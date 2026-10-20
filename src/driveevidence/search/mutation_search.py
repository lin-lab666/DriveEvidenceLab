"""Mutation-driven scenario search starting from seed failures."""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.search.base import BaseSearchMethod, Budget, FailureCandidate, SearchReport
from driveevidence.search.random_search import RandomSearch
from driveevidence.sim.base import EpisodeResult, FailureCategory, SimulatorAdapter


class MutationSearch(BaseSearchMethod):
    """Mutate discovered failure scenarios to find nearby counter-examples."""

    name = "mutation"

    def __init__(self, *, road_length_m: float = 500.0, lanes: int = 3,
                 lane_width_m: float = 3.7, speed_limit_mps: float = 33.0,
                 max_steps: int = 100, mutate_from_archive_prob: float = 0.7):
        self.road_length_m = road_length_m
        self.lanes = lanes
        self.lane_width_m = lane_width_m
        self.speed_limit_mps = speed_limit_mps
        self.max_steps = max_steps
        self.mutate_from_archive_prob = mutate_from_archive_prob

    def _random_init(self, rng: np.random.Generator, round_idx: int) -> ScenarioIR:
        # Delegate to random search prior for fresh initialization.
        rs = RandomSearch(
            road_length_m=self.road_length_m,
            lanes=self.lanes,
            lane_width_m=self.lane_width_m,
            speed_limit_mps=self.speed_limit_mps,
            max_steps=self.max_steps,
        )
        return rs._sample_scenario(rng, round_idx)

    def _mutate(self, base: ScenarioIR, rng: np.random.Generator,
                round_idx: int) -> ScenarioIR:
        # Copy base and perturb key parameters.
        ego = VehicleState(**base.ego.to_dict())
        vehicles = [VehicleState(**v.to_dict()) for v in base.vehicles]

        op = rng.choice(["ego_v", "lead_gap", "lead_v", "lane"])
        if op == "ego_v":
            ego.v_mps = float(np.clip(
                ego.v_mps + rng.uniform(-5.0, 5.0), 0.0, self.speed_limit_mps
            ))
        elif op == "lead_gap" and vehicles:
            lead = vehicles[0]
            new_gap = lead.x_m - ego.x_m
            factor = float(rng.uniform(0.65, 0.95))
            new_gap = max(3.0, new_gap * factor)
            lead.x_m = ego.x_m + new_gap
        elif op == "lead_v" and vehicles:
            vehicles[0].v_mps = float(np.clip(
                vehicles[0].v_mps + rng.uniform(-5.0, 5.0), 0.0, self.speed_limit_mps
            ))
        elif op == "lane" and vehicles:
            lane = int(np.clip(
                round((vehicles[0].y_m / self.lane_width_m) - 0.5) + rng.integers(-1, 2),
                0, self.lanes - 1
            ))
            vehicles[0].y_m = (lane + 0.5) * self.lane_width_m

        return ScenarioIR(
            scenario_id=f"mut_{round_idx:04d}",
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
        archive: List[ScenarioIR] = list(seed_scenarios or [])
        round_idx = 0

        while not budget.exhausted:
            budget.register_launch()
            if archive and rng.random() < self.mutate_from_archive_prob:
                base = archive[int(rng.integers(0, len(archive)))]
                scenario = self._mutate(base, rng, round_idx)
            else:
                scenario = self._random_init(rng, round_idx)

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
                archive.append(scenario)

            round_idx += 1

        return SearchReport(
            method=self.name,
            master_seed=master_seed,
            budget_snapshot=budget.snapshot(),
            candidates=candidates,
            n_episodes=round_idx,
            episode_summaries=summaries,
        )
