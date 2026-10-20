"""Deterministic kinematic simulator for straight-road scenarios.

This is an intentionally simplified backend for unit tests, property tests
and replay consistency checks. It is NOT a realistic dynamics model and must
not be confused with real-world validation.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from driveevidence.planners.rule_based import PlannerContext, get_planner
from driveevidence.scenario.ir import ScenarioIR, ScenarioValidationError, VehicleState
from driveevidence.sim.base import (
    EpisodeResult,
    FailureCategory,
    SimulatorAdapter,
    TrajectorySample,
    register_adapter,
)


class _Box:
    def __init__(self, x: float, y: float, heading: float, length: float, width: float):
        self.x = x
        self.y = y
        self.heading = heading
        self.length = length
        self.width = width

    def corners(self) -> List[tuple]:
        c = math.cos(self.heading)
        s = math.sin(self.heading)
        dx_long = (self.length / 2.0) * c
        dy_long = (self.length / 2.0) * s
        dx_lat = (self.width / 2.0) * (-s)
        dy_lat = (self.width / 2.0) * c
        return [
            (self.x + dx_long + dx_lat, self.y + dy_long + dy_lat),
            (self.x + dx_long - dx_lat, self.y + dy_long - dy_lat),
            (self.x - dx_long - dx_lat, self.y - dy_long - dy_lat),
            (self.x - dx_long + dx_lat, self.y - dy_long + dy_lat),
        ]


def _obb_intersect(a: _Box, b: _Box) -> bool:
    """Separating-axis theorem for two rectangles."""
    axes = [
        (math.cos(a.heading), math.sin(a.heading)),
        (math.cos(a.heading + math.pi / 2), math.sin(a.heading + math.pi / 2)),
        (math.cos(b.heading), math.sin(b.heading)),
        (math.cos(b.heading + math.pi / 2), math.sin(b.heading + math.pi / 2)),
    ]
    for ax, ay in axes:
        a_min = a_max = None
        for cx, cy in a.corners():
            proj = cx * ax + cy * ay
            if a_min is None or proj < a_min:
                a_min = proj
            if a_max is None or proj > a_max:
                a_max = proj
        b_min = b_max = None
        for cx, cy in b.corners():
            proj = cx * ax + cy * ay
            if b_min is None or proj < b_min:
                b_min = proj
            if b_max is None or proj > b_max:
                b_max = proj
        if a_max < b_min or b_max < a_min:
            return False
    return True


@register_adapter
class KinematicBuiltinAdapter(SimulatorAdapter):
    """Simple deterministic straight-road simulator."""

    name = "builtin"
    version = "builtin/1.1"

    def capabilities(self) -> Dict[str, bool]:
        return {
            "collision": True,
            "off_road": True,
            "rule_violation": True,
            "near_miss": True,
            "timeout": True,
            "deterministic_replay": True,
        }

    def run_episode(
        self,
        scenario: ScenarioIR,
        seed: int,
        planner_name: str = "default",
        config: Optional[Dict[str, Any]] = None,
    ) -> EpisodeResult:
        config = config or {}
        try:
            scenario.validate()
        except ScenarioValidationError as exc:
            return EpisodeResult(
                scenario_id=scenario.scenario_id,
                scenario_hash=scenario.scenario_hash,
                adapter_name=self.name,
                adapter_version=self.version,
                planner_name=planner_name,
                seed=seed,
                steps=0,
                wall_time_s=0.0,
                terminated=False,
                truncated=False,
                failure_category=FailureCategory.INFEASIBLE,
                failure_detail=f"scenario invalid: {exc}",
                trajectory=[],
                metrics={},
                raw={"infeasible_reason": str(exc)},
            )

        dt = float(config.get("dt", 0.1))
        max_steps = int(config.get("max_steps", 300))
        rule_speed_tol = float(config.get("rule_speed_tolerance_mps", 2.0))
        near_miss_gap_m = float(config.get("near_miss_gap_m", 1.0))
        near_miss_ttc_s = float(config.get("near_miss_ttc_s", 1.5))

        # Use seed only for reproducibility audit; default no randomness.
        rng = np.random.default_rng(seed)

        if planner_name == "default":
            planner_name = "safe_follow"
        planner = get_planner(planner_name)

        # deep-ish copy of vehicles so original ScenarioIR stays immutable
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
        for step in range(max_steps):
            # record sample
            trajectory.append(
                TrajectorySample(t=t, x=ego.x_m, y=ego.y_m, v=ego.v_mps, heading=ego.heading_rad)
            )

            # off-road check (ego only)
            road_width = scenario.lanes * scenario.lane_width_m
            if ego.y_m - ego.width_m / 2.0 < 0.0 or ego.y_m + ego.width_m / 2.0 > road_width:
                category = FailureCategory.OFF_ROAD
                detail = f"ego y={ego.y_m:.2f} outside [0, {road_width:.2f}]"
                break

            # rule violation
            if ego.v_mps > scenario.speed_limit_mps + rule_speed_tol:
                category = FailureCategory.RULE_VIOLATION
                detail = f"speed {ego.v_mps:.2f} > limit+tol {scenario.speed_limit_mps + rule_speed_tol:.2f}"
                break

            # collision check with all others
            ego_box = _Box(ego.x_m, ego.y_m, ego.heading_rad, ego.length_m, ego.width_m)
            collided_with = None
            for other in others:
                other_box = _Box(
                    other.x_m, other.y_m, other.heading_rad, other.length_m, other.width_m
                )
                if _obb_intersect(ego_box, other_box):
                    collided_with = other.id
                    break
            if collided_with is not None:
                category = FailureCategory.COLLISION
                detail = f"collision with vehicle {collided_with} at t={t:.2f}"
                break

            # near-miss bookkeeping (no break)
            for other in others:
                dx = other.x_m - ego.x_m - (other.length_m + ego.length_m) / 2.0
                dy = other.y_m - ego.y_m
                if dx > 0:
                    gap = math.hypot(dx, dy)
                    metrics["min_gap_m"] = min(metrics["min_gap_m"], gap)
                    rel_speed = max(0.0, ego.v_mps - other.v_mps)
                    if rel_speed > 0.01:
                        ttc = dx / rel_speed
                        metrics["min_ttc_s"] = min(metrics["min_ttc_s"], ttc)

            metrics["max_v_mps"] = max(metrics["max_v_mps"], ego.v_mps)
            metrics["final_x_m"] = ego.x_m

            # step dynamics
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

            # others move at constant velocity straight
            for other in others:
                other.x_m += other.v_mps * math.cos(other.heading_rad) * dt
                other.y_m += other.v_mps * math.sin(other.heading_rad) * dt

            # ego moves straight (planners do not change heading in builtin)
            ego.x_m += ego.v_mps * math.cos(ego.heading_rad) * dt
            ego.y_m += ego.v_mps * math.sin(ego.heading_rad) * dt
            t += dt

        else:
            trajectory.append(
                TrajectorySample(t=t, x=ego.x_m, y=ego.y_m, v=ego.v_mps, heading=ego.heading_rad)
            )
            # Near-miss must be evaluated *here*: the for/else guarantees that a
            # loop which ran to completion leaves category == TIMEOUT, so an
            # `if category == NONE` check after the loop was unreachable dead
            # code and NEAR_MISS could never be reported (found by the Gate E
            # audit, DECISIONS D017).
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

        terminated = category in {
            FailureCategory.COLLISION,
            FailureCategory.OFF_ROAD,
            FailureCategory.RULE_VIOLATION,
        }
        truncated = category in {FailureCategory.TIMEOUT, FailureCategory.NEAR_MISS}

        return EpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario.scenario_hash,
            adapter_name=self.name,
            adapter_version=self.version,
            planner_name=planner_name,
            seed=seed,
            steps=len(trajectory),
            wall_time_s=wall_time_s,
            terminated=terminated,
            truncated=truncated,
            failure_category=category,
            failure_detail=detail,
            trajectory=trajectory,
            metrics=metrics,
            raw={"dt": dt, "max_steps": max_steps},
        )
