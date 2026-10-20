"""Tests for search methods using a deterministic mock adapter."""
import unittest

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.search.base import Budget
from driveevidence.search.mutation_search import MutationSearch
from driveevidence.search.random_search import RandomSearch
from driveevidence.sim.base import (
    EpisodeResult,
    FailureCategory,
    SimulatorAdapter,
    TrajectorySample,
)


class MockAdapter(SimulatorAdapter):
    """Deterministic test adapter: collision if ego speed > 24 m/s."""

    name = "mock"
    version = "mock/1.0"

    def capabilities(self):
        return {
            "collision": True,
            "off_road": True,
            "rule_violation": True,
            "near_miss": False,
            "timeout": True,
            "deterministic_replay": True,
        }

    def run_episode(self, scenario, seed, planner_name="default", config=None):
        if scenario.ego.v_mps > 24.0:
            category = FailureCategory.COLLISION
            detail = "mock collision: high speed"
            steps = 1
            terminated = True
        else:
            category = FailureCategory.NONE
            detail = "safe"
            steps = 10
            terminated = False
        return EpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario.scenario_hash,
            adapter_name=self.name,
            adapter_version=self.version,
            planner_name=planner_name,
            seed=seed,
            steps=steps,
            wall_time_s=0.001,
            terminated=terminated,
            truncated=False,
            failure_category=category,
            failure_detail=detail,
            trajectory=[TrajectorySample(t=0, x=0, y=0, v=scenario.ego.v_mps, heading=0)],
            metrics={"max_v_mps": scenario.ego.v_mps},
        )


class SearchTests(unittest.TestCase):
    def test_random_search_budget_invariant(self):
        adapter = MockAdapter()
        budget = Budget(max_episodes=32)
        search = RandomSearch(road_length_m=500, lanes=3, max_steps=10)
        report = search.search(adapter, budget, master_seed=123)
        snap = report.budget_snapshot
        self.assertEqual(snap["launched"], 32)
        self.assertEqual(
            snap["completed"] + snap["failed"] + snap["cancelled"] + snap["infeasible"],
            snap["launched"],
        )
        self.assertEqual(report.n_episodes, 32)

    def test_random_search_finds_failures(self):
        adapter = MockAdapter()
        budget = Budget(max_episodes=64)
        search = RandomSearch(road_length_m=500, lanes=3, max_steps=10)
        report = search.search(adapter, budget, master_seed=456)
        # Mock collision rate is around (33-25)/(33-15) ~ 0.44, so expect >0.
        self.assertGreater(len(report.candidates), 0)
        self.assertTrue(all(c.failure_category == "collision" for c in report.candidates))

    def test_mutation_search_budget_invariant(self):
        adapter = MockAdapter()
        budget = Budget(max_episodes=32)
        search = MutationSearch(road_length_m=500, lanes=3, max_steps=10)
        report = search.search(adapter, budget, master_seed=789)
        snap = report.budget_snapshot
        self.assertEqual(snap["launched"], 32)
        self.assertEqual(
            snap["completed"] + snap["failed"] + snap["cancelled"] + snap["infeasible"],
            snap["launched"],
        )

    def test_mutation_search_finds_failures(self):
        adapter = MockAdapter()
        budget = Budget(max_episodes=64)
        search = MutationSearch(road_length_m=500, lanes=3, max_steps=10)
        report = search.search(adapter, budget, master_seed=999)
        self.assertGreater(len(report.candidates), 0)

    def test_mutation_search_from_seed_scenarios(self):
        adapter = MockAdapter()
        seed = ScenarioIR(
            scenario_id="seed",
            road_length_m=500,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50, y_m=1.85, v_mps=26.0, heading_rad=0.0),
            vehicles=[],
        )
        budget = Budget(max_episodes=32)
        search = MutationSearch(road_length_m=500, lanes=3, max_steps=10)
        report = search.search(adapter, budget, master_seed=111, seed_scenarios=[seed])
        # Starting from a known collision scenario should quickly produce candidates.
        self.assertGreater(len(report.candidates), 0)

    def test_determinism(self):
        adapter = MockAdapter()
        budget1 = Budget(max_episodes=32)
        budget2 = Budget(max_episodes=32)
        search = RandomSearch(road_length_m=500, lanes=3, max_steps=10)
        r1 = search.search(adapter, budget1, master_seed=555)
        r2 = search.search(adapter, budget2, master_seed=555)
        self.assertEqual(len(r1.episode_summaries), len(r2.episode_summaries))
        for a, b in zip(r1.episode_summaries, r2.episode_summaries):
            self.assertEqual(a["failure_category"], b["failure_category"])


if __name__ == "__main__":
    unittest.main()
