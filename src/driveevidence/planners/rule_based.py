"""Rule-based planners for straight-road scenarios.

These are intentionally simple controllers used as reproducible baselines,
not as production autonomous-driving policies. No real-road safety claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class PlannerContext:
    ego: "VehicleState"  # forward ref ok in runtime via duck typing
    others: List["VehicleState"]
    dt: float
    speed_limit_mps: float
    road_length_m: float
    lanes: int
    lane_width_m: float


PlannerFn = Callable[[PlannerContext], float]


class _VehicleStub:
    """Minimal duck-typed vehicle used by planner logic."""

    def __init__(self, v):
        object.__setattr__(self, "__dict__", v)


class PlannerRegistry:
    """Lightweight registry of planner callables."""

    def __init__(self) -> None:
        self._planners: Dict[str, PlannerFn] = {}

    def register(self, name: str, fn: Optional[PlannerFn] = None) -> Any:
        if fn is not None:
            self._planners[name] = fn
            return fn

        def decorator(f: PlannerFn) -> PlannerFn:
            self._planners[name] = f
            return f

        return decorator

    def get(self, name: str) -> PlannerFn:
        if name not in self._planners:
            raise KeyError(f"unknown planner {name!r}; available: {sorted(self._planners)}")
        return self._planners[name]

    def list(self) -> List[str]:
        return sorted(self._planners)


_REGISTRY = PlannerRegistry()


def get_planner(name: str) -> PlannerFn:
    """Return planner callable by name."""
    return _REGISTRY.get(name)


def list_planners() -> List[str]:
    return _REGISTRY.list()


def _find_lead(ctx: PlannerContext) -> Optional[_VehicleStub]:
    """Return the closest vehicle ahead in roughly the same lane strip."""
    ego = ctx.ego
    lane_width = ctx.lane_width_m
    candidates = []
    for v in ctx.others:
        if v.id == ego.id:
            continue
        dy = abs(v.y_m - ego.y_m)
        if dy > lane_width:
            continue
        dx = v.x_m - ego.x_m
        if dx <= 0:
            continue
        candidates.append((dx, v))
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[0])[1]


@_REGISTRY.register("constant_speed")
def constant_speed(ctx: PlannerContext) -> float:
    """Hold current speed."""
    return 0.0


@_REGISTRY.register("safe_follow")
def safe_follow(ctx: PlannerContext) -> float:
    """IDM-lite longitudinal controller: keep safe gap and target speed."""
    ego = ctx.ego
    lead = _find_lead(ctx)
    target = ctx.speed_limit_mps
    if lead is None:
        if ego.v_mps < target:
            return 2.0
        return 0.0

    # gap between rear of lead and front of ego (center-to-center minus half lengths)
    gap = lead.x_m - ego.x_m - (lead.length_m + ego.length_m) / 2.0
    gap = max(0.0, gap)
    desired_gap = 2.0 * ego.v_mps  # 2 s headway

    if gap < 0.5 * desired_gap:
        return -9.0
    if gap < desired_gap:
        ratio = (desired_gap - gap) / (0.5 * desired_gap)
        return -6.0 * min(1.0, ratio)
    if ego.v_mps < target:
        return 2.0
    return 0.0


def default_planner() -> str:
    return "safe_follow"
