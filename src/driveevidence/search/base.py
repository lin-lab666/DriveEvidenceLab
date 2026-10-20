"""Search framework: budget accounting, candidate archive, and report contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from driveevidence.scenario.ir import ScenarioIR
from driveevidence.sim.base import EpisodeResult, SimulatorAdapter


@dataclass
class Budget:
    """Mutable budget/counter container. Invariant checked on every update."""

    max_episodes: int
    planned: int = 0
    launched: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    infeasible: int = 0

    def register_launch(self) -> None:
        if self.launched >= self.max_episodes:
            raise RuntimeError("budget exhausted: cannot launch more episodes")
        self.launched += 1

    def register_complete(self) -> None:
        self.completed += 1
        self._check()

    def register_fail(self) -> None:
        self.failed += 1
        self._check()

    def register_cancel(self) -> None:
        self.cancelled += 1
        self._check()

    def register_infeasible(self) -> None:
        self.infeasible += 1
        self._check()

    def _check(self) -> None:
        total = self.completed + self.failed + self.cancelled + self.infeasible
        if total > self.launched:
            raise RuntimeError(
                f"budget invariant violated: completed+failed+cancelled+infeasible "
                f"({total}) > launched ({self.launched})"
            )
        if self.launched > self.max_episodes:
            raise RuntimeError(
                f"budget invariant violated: launched ({self.launched}) > "
                f"max_episodes ({self.max_episodes})"
            )

    @property
    def exhausted(self) -> bool:
        return self.launched >= self.max_episodes

    @property
    def remaining(self) -> int:
        return max(0, self.max_episodes - self.launched)

    def snapshot(self) -> Dict[str, int]:
        return {
            "max_episodes": self.max_episodes,
            "planned": self.planned,
            "launched": self.launched,
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "infeasible": self.infeasible,
        }


@dataclass
class FailureCandidate:
    scenario_hash: str
    scenario_dict: Dict[str, Any]
    discovery_seed: int
    failure_category: str
    discovery_method: str
    round_idx: int
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SearchReport:
    method: str
    master_seed: int
    budget_snapshot: Dict[str, int]
    candidates: List[FailureCandidate]
    n_episodes: int
    episode_summaries: List[Dict[str, Any]]

    def failure_categories(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for c in self.candidates:
            counts[c.failure_category] = counts.get(c.failure_category, 0) + 1
        return counts


class BaseSearchMethod(ABC):
    """Abstract search strategy."""

    name: str = "abstract"

    @abstractmethod
    def search(
        self,
        adapter: SimulatorAdapter,
        budget: Budget,
        master_seed: int,
        seed_scenarios: Optional[List[ScenarioIR]] = None,
    ) -> SearchReport:
        """Run search within the given budget."""
