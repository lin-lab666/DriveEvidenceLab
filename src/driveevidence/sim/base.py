"""Simulator adapter protocol and episode result contract (sim/v1).

Every claimed result must be traceable to raw records produced through
this interface. Failure categories are reported ONLY for categories the
adapter explicitly supports (see SimulatorAdapter.capabilities()).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from driveevidence.scenario.ir import ScenarioIR


class FailureCategory(str, Enum):
    NONE = "none"
    COLLISION = "collision"
    OFF_ROAD = "off_road"
    RULE_VIOLATION = "rule_violation"
    NEAR_MISS = "near_miss"
    INFEASIBLE = "infeasible"
    SIMULATOR_ERROR = "simulator_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class TrajectorySample:
    t: float
    x: float
    y: float
    v: float
    heading: float

    def to_dict(self) -> Dict[str, float]:
        return {"t": self.t, "x": self.x, "y": self.y, "v": self.v, "heading": self.heading}


@dataclass
class EpisodeResult:
    """Outcome of one simulated episode. Fully JSON-serializable."""

    scenario_id: str
    scenario_hash: str
    adapter_name: str
    adapter_version: str
    planner_name: str
    seed: int
    steps: int
    wall_time_s: float
    terminated: bool
    truncated: bool
    failure_category: FailureCategory
    failure_detail: str
    trajectory: List[TrajectorySample] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_hash": self.scenario_hash,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "planner_name": self.planner_name,
            "seed": self.seed,
            "steps": self.steps,
            "wall_time_s": self.wall_time_s,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "failure_category": self.failure_category.value,
            "failure_detail": self.failure_detail,
            "trajectory": [s.to_dict() for s in self.trajectory],
            "metrics": dict(self.metrics),
            "raw": _json_safe(self.raw),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EpisodeResult":
        return cls(
            scenario_id=d["scenario_id"],
            scenario_hash=d["scenario_hash"],
            adapter_name=d["adapter_name"],
            adapter_version=d["adapter_version"],
            planner_name=d["planner_name"],
            seed=d["seed"],
            steps=d["steps"],
            wall_time_s=d["wall_time_s"],
            terminated=d["terminated"],
            truncated=d["truncated"],
            failure_category=FailureCategory(d["failure_category"]),
            failure_detail=d["failure_detail"],
            trajectory=[TrajectorySample(**s) for s in d["trajectory"]],
            metrics=dict(d["metrics"]),
            raw=d.get("raw", {}),
        )


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(obj)


class SimulatorAdapter(ABC):
    """Contract every simulation backend must fulfill."""

    #: short registry name, e.g. "builtin", "highwayenv"
    name: str = "abstract"
    #: backend software version string (the REAL one, queried at runtime)
    version: str = "unknown"

    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """Declare supported failure categories & features.

        Keys (all required): collision, off_road, rule_violation, near_miss,
        timeout, deterministic_replay.
        Adapters MUST NOT report categories they cannot detect.
        """

    @abstractmethod
    def run_episode(self, scenario: ScenarioIR, seed: int,
                    planner_name: str = "default",
                    config: Optional[Dict[str, Any]] = None) -> EpisodeResult:
        """Run one episode. Must be deterministic given (scenario, seed,
        planner_name, config): identical inputs => identical failure_category
        and metrics (wall_time_s exempt)."""


# ---------------- adapter registry ----------------
_REGISTRY: Dict[str, type] = {}


def register_adapter(cls: type) -> type:
    if not issubclass(cls, SimulatorAdapter):
        raise TypeError(f"{cls} is not a SimulatorAdapter")
    _REGISTRY[cls.name] = cls
    return cls


def create_adapter(name: str, **kwargs: Any) -> SimulatorAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"adapter {name!r} not registered; available: {sorted(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)


def list_adapters() -> List[str]:
    return sorted(_REGISTRY)
