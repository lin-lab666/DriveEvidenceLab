"""Random scenario sampling baseline."""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.search.base import BaseSearchMethod, Budget, FailureCandidate, SearchReport
from driveevidence.sim.base import EpisodeResult, FailureCategory, SimulatorAdapter


class RandomSearch(BaseSearchMethod):
    """Sample scenarios from a fixed prior and run episodes until budget exhausts."""

    name = "random"

    def __init__(self, *, road_length_m: float = 500.0, lanes: int = 3,
                 lane_width_m: float = 3.7, speed_limit_mps: float = 33.0,
                 max_steps: int = 100):
        self.road_length_m = road_length_m
        self.lanes = lanes
        self.lane_width_m = lane_width_m
        self.speed_limit_mps = speed_limit_mps
        self.max_steps = max_steps

    def _sample_scenario(self, rng: np.random.Generator, round_idx: int) -> ScenarioIR:
        ego_lane = int(rng.integers(0, self.lanes))
        ego_y = (ego_lane + 0.5) * self.lane_width_m
        ego_v = float(rng.uniform(15.0, self.speed_limit_mps))
        ego = VehicleState(
            id="ego", x_m=50.0, y_m=ego_y, v_mps=ego_v, heading_rad=0.0
        )
        vehicles: List[VehicleState] = []
        if rng.random() < 0.7:
            lead_lane = min(
                self.lanes - 1, max(0, int(ego_lane + rng.integers(-1, 2)))
            )
            lead_y = (lead_lane + 0.5) * self.lane_width_m
            lead_v = float(rng.uniform(5.0, min(25.0, ego_v + 5.0)))
            lead_gap = float(rng.uniform(8.0, 60.0))
            vehicles.append(
                VehicleState(
                    id="v1",
                    x_m=50.0 + lead_gap,
                    y_m=lead_y,
                    v_mps=lead_v,
                    heading_rad=0.0,
                )
            )
        return ScenarioIR(
            scenario_id=f"rand_{round_idx:04d}",
            road_length_m=self.road_length_m,
            lanes=self.lanes,
            lane_width_m=self.lane_width_m,
            speed_limit_mps=self.speed_limit_mps,
            ego=ego,
            vehicles=vehicles,
        )

    def search(
        self,
        adapter: SimulatorAdapter,
        budget: Budget,
        master_seed: int,
        seed_scenarios: Optional[List[ScenarioIR]] = None,
    ) -> SearchReport:
        rng = np.random.default_rng(master_seed)
        candidates: List[FailureCandidate] = []
        summaries: List[dict] = []
        round_idx = 0

        while not budget.exhausted:
            budget.register_launch()
            scenario = self._sample_scenario(rng, round_idx)
            try:
                result = adapter.run_episode(
                    scenario, seed=int(rng.integers(0, 2**31)),
                    planner_name="safe_follow",
                    config={"max_steps": self.max_steps},
                )
            except Exception as exc:
                budget.register_fail()
                summaries.append({
                    "scenario_hash": scenario.scenario_hash,
                    "seed": -1,
                    "failure_category": FailureCategory.SIMULATOR_ERROR.value,
                    "failure_detail": str(exc),
                })
                round_idx += 1
                continue

            if result.failure_category == FailureCategory.INFEASIBLE:
                budget.register_infeasible()
            else:
                budget.register_complete()

            summaries.append({
                "scenario_hash": result.scenario_hash,
                "seed": result.seed,
                "failure_category": result.failure_category.value,
                "steps": result.steps,
            })

            if result.failure_category in {
                FailureCategory.COLLISION,
                FailureCategory.OFF_ROAD,
                FailureCategory.NEAR_MISS,
                FailureCategory.RULE_VIOLATION,
            }:
                candidates.append(
                    FailureCandidate(
                        scenario_hash=result.scenario_hash,
                        scenario_dict=scenario.to_dict(),
                        discovery_seed=result.seed,
                        failure_category=result.failure_category.value,
                        discovery_method=self.name,
                        round_idx=round_idx,
                        metrics=dict(result.metrics),
                    )
                )

            round_idx += 1

        return SearchReport(
            method=self.name,
            master_seed=master_seed,
            budget_snapshot=budget.snapshot(),
            candidates=candidates,
            n_episodes=round_idx,
            episode_summaries=summaries,
        )
