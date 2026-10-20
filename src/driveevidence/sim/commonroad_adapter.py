"""CommonRoad interoperability backend.

Verified against ``commonroad-io 2026.1`` (installed on demand; this module is
imported lazily so the rest of the package keeps working without it).

SCOPE — read this before quoting any number produced here
---------------------------------------------------------
This is **not** a second dynamics engine. It reuses the same simple kinematic
rollout as :mod:`driveevidence.sim.builtin` (ego follows the planner, other
vehicles hold constant velocity) and replaces only the **judging layer**:

* scenario validity is checked by CommonRoad's own writer (``check_validity``);
* the scenario is exchanged through CommonRoad's XML format;
* collisions are decided by CommonRoad ``RectObstacleShape`` occupancies
  (shapely polygon intersection) instead of our in-house OBB test;
* off-road is decided by testing the ego occupancy against the union of the
  lanelet polygons of a CommonRoad ``LaneletNetwork``.

That makes it a genuine **cross-check of the failure taxonomy** against a real
third-party implementation, which is what the adapter interface needs before a
CommonRoad dynamics simulator is plugged in. It does **not** constitute an
independent simulation study, and results from it must not be pooled with
``builtin`` numbers.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from driveevidence.planners.rule_based import PlannerContext, get_planner
from driveevidence.scenario.ir import ScenarioIR, ScenarioValidationError, VehicleState
from driveevidence.sim.base import (
    EpisodeResult,
    FailureCategory,
    SimulatorAdapter,
    TrajectorySample,
    register_adapter,
)

_HINT = (
    "the 'commonroad' backend requires commonroad-io; install it with "
    "`pip install commonroad-io` (verified against 2026.1)"
)


def _import_commonroad():
    """Import the CommonRoad stack lazily and fail with an actionable message."""
    try:
        from commonroad.common.common_scenario import ScenarioID
        from commonroad.common.file_reader import CommonRoadFileReader
        from commonroad.common.file_writer import (
            CommonRoadFileWriter,
            FileFormat,
            OverwriteExistingFile,
        )
        from commonroad.geometry.obstacle_shapes.rect_obstacle_shape import RectObstacleShape
        from commonroad.planning.planning_problem import PlanningProblemSet
        from commonroad.scenario.lanelet import Lanelet, LaneletNetwork, LaneletType
        from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
        from commonroad.scenario.scenario import Scenario as CRScenario
        from commonroad.scenario.scenario import Tag
        from commonroad.scenario.state import InitialState, KSState
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(_HINT) from exc
    return {
        "ScenarioID": ScenarioID,
        "CommonRoadFileReader": CommonRoadFileReader,
        "CommonRoadFileWriter": CommonRoadFileWriter,
        "FileFormat": FileFormat,
        "OverwriteExistingFile": OverwriteExistingFile,
        "RectObstacleShape": RectObstacleShape,
        "PlanningProblemSet": PlanningProblemSet,
        "Lanelet": Lanelet,
        "LaneletType": LaneletType,
        "LaneletNetwork": LaneletNetwork,
        "DynamicObstacle": DynamicObstacle,
        "ObstacleType": ObstacleType,
        "CRScenario": CRScenario,
        "Tag": Tag,
        "InitialState": InitialState,
        "KSState": KSState,
    }


def commonroad_version() -> Optional[str]:
    """Return the installed commonroad-io version, or ``None`` if absent."""
    try:
        from importlib.metadata import version

        return version("commonroad-io")
    except Exception:  # pragma: no cover - metadata missing on exotic installs
        return None


# ---------------------------------------------------------------------------
# Scenario exchange
# ---------------------------------------------------------------------------
def _boundary(x0: float, x1: float, y: float, step: float = 50.0) -> Any:
    import numpy as np

    xs = np.arange(x0, x1 + 1e-9, step)
    if xs[-1] < x1:
        xs = np.append(xs, x1)
    return np.array([[float(x), float(y)] for x in xs])


def build_commonroad_scenario(scenario: ScenarioIR) -> Any:
    """Map a :class:`ScenarioIR` onto a real ``commonroad.scenario.Scenario``.

    Only the subset representable in IR v1 is mapped: a straight road with
    ``lanes`` parallel lanelets covering ``[0, road_length_m] x [0, lanes*lane_width_m]``,
    the ego vehicle and every other vehicle as rectangular dynamic obstacles.
    """
    cr = _import_commonroad()
    network = cr["LaneletNetwork"]()
    for i in range(scenario.lanes):
        y_lo = i * scenario.lane_width_m
        y_hi = (i + 1) * scenario.lane_width_m
        left = _boundary(0.0, scenario.road_length_m, y_hi)
        right = _boundary(0.0, scenario.road_length_m, y_lo)
        network.add_lanelet(
            cr["Lanelet"](
                left_vertices=left,
                center_vertices=(left + right) / 2.0,
                right_vertices=right,
                lanelet_id=100 + i,
                # Without an explicit type CommonRoad's writer emits one
                # UserWarning per lanelet; these are plain motorway lanes.
                lanelet_type={cr["LaneletType"].HIGHWAY},
            )
        )

    cr_scenario = cr["CRScenario"](
        dt=0.1,
        scenario_id=cr["ScenarioID"](
            map_name=_safe_map_name(scenario.scenario_id), map_id=1
        ),
        tags={cr["Tag"].HIGHWAY},
    )
    cr_scenario.replace_lanelet_network(network)

    obstacles = []
    for idx, vehicle in enumerate([scenario.ego] + list(scenario.vehicles)):
        obstacles.append(
            cr["DynamicObstacle"](
                obstacle_id=idx + 1,
                obstacle_type=cr["ObstacleType"].CAR,
                obstacle_shape=cr["RectObstacleShape"](
                    width=float(vehicle.width_m), length=float(vehicle.length_m)
                ),
                initial_state=cr["InitialState"](
                    time_step=0,
                    position=_np_array([vehicle.x_m, vehicle.y_m]),
                    orientation=float(vehicle.heading_rad),
                    velocity=float(vehicle.v_mps),
                ),
                prediction=None,
            )
        )
    if obstacles:
        cr_scenario.add_objects(obstacles)
    return cr_scenario


def _np_array(values: List[float]) -> Any:
    import numpy as np

    return np.array([float(v) for v in values])


def _safe_map_name(scenario_id: str) -> str:
    """CommonRoad map names must be alphanumeric; sanitise deterministically."""
    cleaned = "".join(ch for ch in scenario_id if ch.isalnum())[:24]
    return cleaned or "DELab"


def exchange_roundtrip(scenario: ScenarioIR, directory: str) -> Dict[str, Any]:
    """Write the scenario as CommonRoad XML, read it back, and compare.

    Returns a dict describing what was compared, so a caller can assert on it
    rather than trusting a bare boolean.
    """
    cr = _import_commonroad()
    import os

    cr_scenario = build_commonroad_scenario(scenario)
    base = os.path.join(directory, "DELab-1.xml")
    # CommonRoad's writer prompts when the target exists; removing it first keeps
    # this call non-interactive when the same temp path is reused.
    if os.path.exists(base):
        os.remove(base)
    cr["CommonRoadFileWriter"](
        cr_scenario,
        cr["PlanningProblemSet"](),
        author="DriveEvidenceLab",
        affiliation="",
        source="",
        file_format=cr["FileFormat"].XML,
        # CommonRoad's XML writer defaults to 4 decimal places, which loses ~4e-5
        # on velocities. 8 keeps the round-trip within 1e-6 so the comparison
        # below tests the mapping rather than the number formatting (D020).
        decimal_precision=8,
    ).write_to_file(base, cr["OverwriteExistingFile"].ALWAYS, check_validity=True)

    readback, _ = cr["CommonRoadFileReader"](base).open()
    obstacles = readback.dynamic_obstacles
    expected = 1 + len(scenario.vehicles)
    # Obstacle order is not preserved across the XML round-trip, so the ego is
    # identified by the id we assigned (1) rather than by list position.
    ego = next((o for o in obstacles if int(o.obstacle_id) == 1), None)
    return {
        "lanelets_written": scenario.lanes,
        "lanelets_read": len(readback.lanelet_network.lanelets),
        "obstacles_written": expected,
        "obstacles_read": len(obstacles),
        "ego_position": None if ego is None else [float(v) for v in ego.initial_state.position],
        "ego_velocity": None if ego is None else float(ego.initial_state.velocity),
        "ego_length": None if ego is None else float(ego.obstacle_shape.length),
        "ego_width": None if ego is None else float(ego.obstacle_shape.width),
        "xml_bytes": os.path.getsize(base),
    }


# ---------------------------------------------------------------------------
# Judging layer (CommonRoad geometry)
# ---------------------------------------------------------------------------
class CommonRoadJudge:
    """Decides collision / off-road using CommonRoad geometry only."""

    def __init__(self, scenario: ScenarioIR):
        cr = _import_commonroad()
        self._cr = cr
        self._shapes: Dict[Tuple[float, float], Any] = {}
        self._road = None
        network = build_commonroad_scenario(scenario).lanelet_network
        polygons = [ll.convert_to_polygon().shapely_object for ll in network.lanelets]
        if polygons:
            union = polygons[0]
            for poly in polygons[1:]:
                union = union.union(poly)
            self._road = union

    def _occupancy(self, x: float, y: float, heading: float, length: float, width: float) -> Any:
        key = (round(length, 9), round(width, 9))
        shape = self._shapes.get(key)
        if shape is None:
            shape = self._cr["RectObstacleShape"](width=float(width), length=float(length))
            self._shapes[key] = shape
        state = self._cr["KSState"](
            time_step=0,
            position=_np_array([x, y]),
            orientation=float(heading),
            velocity=0.0,
        )
        return shape.compute_occupancy_for_state(state).shapely_object

    def collides(self, ego: VehicleState, other: VehicleState) -> bool:
        a = self._occupancy(ego.x_m, ego.y_m, ego.heading_rad, ego.length_m, ego.width_m)
        b = self._occupancy(
            other.x_m, other.y_m, other.heading_rad, other.length_m, other.width_m
        )
        return bool(a.intersects(b))

    def off_road(self, ego: VehicleState) -> bool:
        # A vehicle is off-road as soon as any part of its footprint leaves the
        # union of drivable lanelets. Using ``within`` on the polygon keeps this
        # a pure CommonRoad/shapely decision with no hand-rolled geometry.
        footprint = self._occupancy(ego.x_m, ego.y_m, ego.heading_rad, ego.length_m, ego.width_m)
        return not footprint.within(self._road)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
@register_adapter
class CommonRoadAdapter(SimulatorAdapter):
    """CommonRoad-geometry backend (scenario exchange + failure taxonomy)."""

    name = "commonroad"

    @property
    def version(self) -> str:  # type: ignore[override]
        found = commonroad_version()
        return f"commonroad-io/{found or 'missing'}+kinematics/1.0"

    def capabilities(self) -> Dict[str, bool]:
        return {
            "collision": True,
            "off_road": True,
            "rule_violation": False,
            "near_miss": True,
            "deterministic_replay": True,
            # Honest flags so nobody mistakes this for a full simulator.
            "commonroad_geometry": True,
            "commonroad_scenario_exchange": True,
            "independent_dynamics": False,
            "third_party_dynamics_engine": False,
        }

    def run_episode(
        self,
        scenario: ScenarioIR,
        seed: int,
        planner_name: str = "safe_follow",
        config: Optional[Dict[str, Any]] = None,
    ) -> EpisodeResult:
        config = config or {}
        try:
            scenario.validate()
        except ScenarioValidationError as exc:
            return _infeasible(self, scenario, seed, planner_name, str(exc))

        dt = float(config.get("dt", 0.1))
        max_steps = int(config.get("max_steps", 300))
        rule_speed_tol = float(config.get("rule_speed_tolerance_mps", 2.0))
        near_miss_gap_m = float(config.get("near_miss_gap_m", 1.0))
        near_miss_ttc_s = float(config.get("near_miss_ttc_s", 1.5))

        if planner_name == "default":
            planner_name = "safe_follow"
        planner = get_planner(planner_name)
        judge = CommonRoadJudge(scenario)

        ego = VehicleState(**scenario.ego.to_dict())
        others = [VehicleState(**v.to_dict()) for v in scenario.vehicles]

        trajectory: List[TrajectorySample] = []
        t = 0.0
        category = FailureCategory.NONE
        detail = ""
        metrics: Dict[str, float] = {
            "min_gap_m": float("inf"),
            "min_ttc_s": float("inf"),
            "max_v_mps": ego.v_mps,
            "final_x_m": ego.x_m,
        }

        start_wall = time.perf_counter()
        for _ in range(max_steps):
            trajectory.append(
                TrajectorySample(
                    t=t, x=ego.x_m, y=ego.y_m, v=ego.v_mps, heading=ego.heading_rad
                )
            )

            if judge.off_road(ego):
                category = FailureCategory.OFF_ROAD
                detail = f"ego footprint leaves lanelet union at t={t:.2f}"
                break

            if ego.v_mps > scenario.speed_limit_mps + rule_speed_tol:
                category = FailureCategory.RULE_VIOLATION
                detail = (
                    f"speed {ego.v_mps:.2f} > limit+tol "
                    f"{scenario.speed_limit_mps + rule_speed_tol:.2f}"
                )
                break

            hit = next((o for o in others if judge.collides(ego, o)), None)
            if hit is not None:
                category = FailureCategory.COLLISION
                detail = f"commonroad occupancy overlap with {hit.id} at t={t:.2f}"
                break

            for other in others:
                dx = other.x_m - ego.x_m - (other.length_m + ego.length_m) / 2.0
                dy = other.y_m - ego.y_m
                if dx > 0:
                    gap = math.hypot(dx, dy)
                    metrics["min_gap_m"] = min(metrics["min_gap_m"], gap)
                    rel_speed = max(0.0, ego.v_mps - other.v_mps)
                    if rel_speed > 0.01:
                        metrics["min_ttc_s"] = min(metrics["min_ttc_s"], dx / rel_speed)

            metrics["max_v_mps"] = max(metrics["max_v_mps"], ego.v_mps)
            metrics["final_x_m"] = ego.x_m

            ctx = PlannerContext(
                ego=ego,
                others=others,
                dt=dt,
                speed_limit_mps=scenario.speed_limit_mps,
                road_length_m=scenario.road_length_m,
                lanes=scenario.lanes,
                lane_width_m=scenario.lane_width_m,
            )
            accel = planner(ctx)
            ego.v_mps = max(0.0, ego.v_mps + accel * dt)
            for other in others:
                other.x_m += other.v_mps * math.cos(other.heading_rad) * dt
                other.y_m += other.v_mps * math.sin(other.heading_rad) * dt
            ego.x_m += ego.v_mps * math.cos(ego.heading_rad) * dt
            ego.y_m += ego.v_mps * math.sin(ego.heading_rad) * dt
            t += dt
        else:
            trajectory.append(
                TrajectorySample(
                    t=t, x=ego.x_m, y=ego.y_m, v=ego.v_mps, heading=ego.heading_rad
                )
            )
            if (
                metrics["min_gap_m"] < near_miss_gap_m
                and metrics["min_ttc_s"] < near_miss_ttc_s
            ):
                category = FailureCategory.NEAR_MISS
                detail = (
                    f"min_gap={metrics['min_gap_m']:.2f}m "
                    f"min_ttc={metrics['min_ttc_s']:.2f}s"
                )
            else:
                category = FailureCategory.TIMEOUT
                detail = f"reached max_steps {max_steps}"

        wall_time_s = time.perf_counter() - start_wall
        if metrics["min_gap_m"] == float("inf"):
            metrics["min_gap_m"] = -1.0
        if metrics["min_ttc_s"] == float("inf"):
            metrics["min_ttc_s"] = -1.0

        return EpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario.scenario_hash,
            adapter_name=self.name,
            adapter_version=self.version,
            planner_name=planner_name,
            seed=seed,
            steps=len(trajectory),
            wall_time_s=wall_time_s,
            terminated=category
            in {
                FailureCategory.COLLISION,
                FailureCategory.OFF_ROAD,
                FailureCategory.RULE_VIOLATION,
            },
            truncated=category in {FailureCategory.TIMEOUT, FailureCategory.NEAR_MISS},
            failure_category=category,
            failure_detail=detail,
            trajectory=trajectory,
            metrics=metrics,
            raw={
                "dt": dt,
                "max_steps": max_steps,
                "rule_speed_tolerance_mps": rule_speed_tol,
                "near_miss_gap_m": near_miss_gap_m,
                "near_miss_ttc_s": near_miss_ttc_s,
                "judge": "commonroad",
                "commonroad_io_version": commonroad_version(),
            },
        )


def _infeasible(
    adapter: CommonRoadAdapter, scenario: ScenarioIR, seed: int, planner: str, reason: str
) -> EpisodeResult:
    return EpisodeResult(
        scenario_id=scenario.scenario_id,
        scenario_hash=scenario.scenario_hash,
        adapter_name=adapter.name,
        adapter_version=adapter.version,
        planner_name=planner,
        seed=seed,
        steps=0,
        wall_time_s=0.0,
        terminated=False,
        truncated=False,
        failure_category=FailureCategory.INFEASIBLE,
        failure_detail=f"scenario invalid: {reason}",
        trajectory=[],
        metrics={},
        raw={"infeasible_reason": reason},
    )
