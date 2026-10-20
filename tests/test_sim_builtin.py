"""Tests for the deterministic kinematic builtin simulator."""
import unittest

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.sim import FailureCategory, create_adapter, list_adapters


class SimBuiltinTests(unittest.TestCase):
    def setUp(self):
        self.adapter = create_adapter("builtin")

    def test_registry(self):
        self.assertIn("builtin", list_adapters())
        caps = self.adapter.capabilities()
        self.assertTrue(caps["collision"])
        self.assertTrue(caps["deterministic_replay"])

    def _base_scenario(self, vehicles=None):
        return ScenarioIR(
            scenario_id="test",
            road_length_m=500.0,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=25.0, heading_rad=0.0),
            vehicles=vehicles or [],
        )

    def test_determinism(self):
        s = self._base_scenario()
        r1 = self.adapter.run_episode(s, seed=42, planner_name="constant_speed")
        r2 = self.adapter.run_episode(s, seed=42, planner_name="constant_speed")
        self.assertEqual(r1.failure_category, r2.failure_category)
        self.assertEqual(len(r1.trajectory), len(r2.trajectory))
        self.assertEqual(r1.metrics["final_x_m"], r2.metrics["final_x_m"])

    def test_timeout(self):
        s = self._base_scenario()
        r = self.adapter.run_episode(s, seed=1, planner_name="constant_speed",
                                      config={"max_steps": 20})
        self.assertEqual(r.failure_category, FailureCategory.TIMEOUT)

    def test_collision(self):
        s = self._base_scenario(
            vehicles=[
                VehicleState(id="v1", x_m=70.0, y_m=1.85, v_mps=5.0, heading_rad=0.0),
            ]
        )
        r = self.adapter.run_episode(s, seed=2, planner_name="constant_speed",
                                      config={"max_steps": 50})
        self.assertEqual(r.failure_category, FailureCategory.COLLISION)
        self.assertIn("v1", r.failure_detail)

    def test_off_road(self):
        s = self._base_scenario()
        s.ego.y_m = 10.0  # close to upper edge of 3-lane road (width 11.1)
        s.ego.heading_rad = 0.8  # heading outward
        r = self.adapter.run_episode(s, seed=3, planner_name="constant_speed",
                                      config={"max_steps": 20})
        self.assertEqual(r.failure_category, FailureCategory.OFF_ROAD)

    def test_rule_violation(self):
        s = self._base_scenario()
        s.ego.v_mps = 40.0  # > 33 + 2
        r = self.adapter.run_episode(s, seed=4, planner_name="constant_speed",
                                      config={"max_steps": 10})
        self.assertEqual(r.failure_category, FailureCategory.RULE_VIOLATION)

    def test_infeasible_overlap(self):
        s = self._base_scenario(
            vehicles=[
                VehicleState(id="v1", x_m=50.0, y_m=1.85, v_mps=10.0, heading_rad=0.0),
            ]
        )
        r = self.adapter.run_episode(s, seed=5)
        self.assertEqual(r.failure_category, FailureCategory.INFEASIBLE)
        self.assertEqual(r.steps, 0)

    def test_safe_follow_avoids_collision(self):
        s = self._base_scenario(
            vehicles=[
                VehicleState(id="v1", x_m=120.0, y_m=1.85, v_mps=10.0, heading_rad=0.0),
            ]
        )
        r = self.adapter.run_episode(s, seed=6, planner_name="safe_follow",
                                      config={"max_steps": 120})
        # Should either reach timeout (no collision) or near_miss; collision is unlikely.
        self.assertNotEqual(r.failure_category, FailureCategory.COLLISION)

    def test_trajectory_shape(self):
        s = self._base_scenario()
        r = self.adapter.run_episode(s, seed=7, planner_name="constant_speed",
                                      config={"max_steps": 10})
        self.assertEqual(len(r.trajectory), r.steps)
        self.assertEqual(r.trajectory[0].v, 25.0)


if __name__ == "__main__":
    unittest.main()


class TestNearMissReachability(unittest.TestCase):
    """Regression test for the NEAR_MISS dead-code defect (DECISIONS D017).

    Before the fix, the for/else always set TIMEOUT on loop completion, so the
    `if category == NONE` near-miss block was unreachable and NEAR_MISS never
    appeared in any run. These tests pin the reachable behaviour.
    """

    def _scenario(self):
        return ScenarioIR(
            scenario_id="near-miss-regression",
            road_length_m=600.0, lanes=3, lane_width_m=3.7, speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=10.4, heading_rad=0.0),
            vehicles=[VehicleState(id="v1", x_m=56.0, y_m=1.85, v_mps=10.0, heading_rad=0.0)],
        )

    def test_near_miss_is_reported_when_thresholds_met(self):
        adapter = create_adapter("builtin")
        # gap 0.54 m (<1.0) and TTC 1.35 s (<1.5) at the horizon, no collision yet
        r = adapter.run_episode(
            self._scenario(), seed=1, planner_name="constant_speed", config={"max_steps": 25}
        )
        self.assertEqual(r.failure_category, FailureCategory.NEAR_MISS)
        self.assertLess(r.metrics["min_gap_m"], 1.0)
        self.assertLess(r.metrics["min_ttc_s"], 1.5)
        self.assertTrue(r.truncated)
        self.assertFalse(r.terminated)

    def test_timeout_still_reported_when_gap_ok(self):
        adapter = create_adapter("builtin")
        # gap 0.74 m but TTC 1.85 s (>1.5): must stay TIMEOUT, not near-miss
        r = adapter.run_episode(
            self._scenario(), seed=1, planner_name="constant_speed", config={"max_steps": 20}
        )
        self.assertEqual(r.failure_category, FailureCategory.TIMEOUT)

    def test_collision_takes_precedence(self):
        adapter = create_adapter("builtin")
        r = adapter.run_episode(
            self._scenario(), seed=1, planner_name="constant_speed", config={"max_steps": 60}
        )
        self.assertEqual(r.failure_category, FailureCategory.COLLISION)


class TestStepCountingSemantics(unittest.TestCase):
    """Pin the documented meaning of EpisodeResult.steps (API.md).

    `steps` counts trajectory samples, not integration steps: a timeout episode
    with max_steps=N reports N+1 samples because the terminal state is appended
    after the loop. The trajectory itself must stay complete and duplicate-free.
    """

    def _scenario(self):
        return ScenarioIR(
            scenario_id="steps",
            road_length_m=2000.0,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=60.0,
            ego=VehicleState(id="ego", x_m=10.0, y_m=1.85, v_mps=20.0, heading_rad=0.0),
            vehicles=[],
        )

    def test_timeout_steps_is_max_steps_plus_one(self):
        adapter = create_adapter("builtin")
        for max_steps in (5, 17, 80):
            with self.subTest(max_steps=max_steps):
                r = adapter.run_episode(
                    self._scenario(), seed=3, planner_name="safe_follow",
                    config={"max_steps": max_steps},
                )
                self.assertEqual(r.failure_category, FailureCategory.TIMEOUT)
                self.assertEqual(r.steps, len(r.trajectory))
                self.assertEqual(r.steps, max_steps + 1)

    def test_trajectory_timestamps_are_contiguous_and_unique(self):
        adapter = create_adapter("builtin")
        r = adapter.run_episode(
            self._scenario(), seed=3, planner_name="safe_follow", config={"max_steps": 40}
        )
        ts = [s.t for s in r.trajectory]
        self.assertEqual(len(ts), len(set(ts)), "timestamps must not repeat")
        self.assertEqual(ts, sorted(ts), "timestamps must be non-decreasing")

    def test_steps_never_exceeds_recording_budget_by_more_than_one(self):
        adapter = create_adapter("builtin")
        for max_steps in (1, 2, 3):
            with self.subTest(max_steps=max_steps):
                r = adapter.run_episode(
                    self._scenario(), seed=3, planner_name="safe_follow",
                    config={"max_steps": max_steps},
                )
                self.assertLessEqual(r.steps, max_steps + 1)
