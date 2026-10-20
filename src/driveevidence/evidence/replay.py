"""Replay an archived episode to verify reproducibility of the outcome.

A mismatch is reported honestly; it does not automatically invalidate the
original result but flags a reproducibility question for the audit trail.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

from driveevidence.evidence.episode_store import EpisodeStore
from driveevidence.scenario.ir import ScenarioIR
from driveevidence.sim.base import EpisodeResult, SimulatorAdapter


@dataclass
class ReplayOutcome:
    original_category: str
    replayed_category: str
    category_match: bool
    metric_diffs: Dict[str, float]
    replayed_result: EpisodeResult


def replay_episode(
    run_dir: str, seq: int, adapter: SimulatorAdapter
) -> ReplayOutcome:
    """Re-run archived episode (same scenario + seed + planner + config)."""
    store = EpisodeStore(run_dir)
    scenario, original_result, extra = store.load(seq)
    kwargs = EpisodeStore.replay_kwargs({
        "result": original_result.to_dict(), "extra": extra
    })
    seed = kwargs["seed"]
    planner_name = kwargs["planner_name"]
    config = kwargs["config"]

    replayed = adapter.run_episode(scenario, seed=seed, planner_name=planner_name, config=config)
    metric_diffs: Dict[str, float] = {}
    for key, orig in original_result.metrics.items():
        if key in replayed.metrics:
            metric_diffs[key] = replayed.metrics[key] - orig

    return ReplayOutcome(
        original_category=original_result.failure_category.value,
        replayed_category=replayed.failure_category.value,
        category_match=(original_result.failure_category == replayed.failure_category),
        metric_diffs=metric_diffs,
        replayed_result=replayed,
    )
