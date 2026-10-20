"""Integration tests for the HighwayEnv adapter (real third-party sim)."""
import unittest

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.sim import create_adapter, list_adapters

try:
    import gymnasium as gym
    import highway_env
    _HAVE_HW = True
except Exception:
    _HAVE_HW = False


@unittest.skipUnless(_HAVE_HW, "highway-env not installed")
class HighwayEnvIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = create_adapter("highwayenv")

    def _base_scenario(self, lead_gap=30.0, ego_speed=25.0, lead_speed=20.0):
        return ScenarioIR(
            scenario_id="hw_test",
            road_length_m=1000.0,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=ego_speed, heading_rad=0.0),
            vehicles=[
                VehicleState(
                    id="v1", x_m=50.0 + lead_gap, y_m=1.85, v_mps=lead_speed, heading_rad=0.0
                ),
            ],
        )

    def test_registry(self):
        self.assertIn("highwayenv", list_adapters())
        caps = self.adapter.capabilities()
        self.assertTrue(caps["collision"])
        self.assertFalse(caps["rule_violation"])

    def test_determinism(self):
        s = self._base_scenario()
        r1 = self.adapter.run_episode(s, seed=100, config={"max_steps": 30})
        r2 = self.adapter.run_episode(s, seed=100, config={"max_steps": 30})
        self.assertEqual(r1.failure_category, r2.failure_category)
        self.assertEqual(r1.steps, r2.steps)

    def test_runs_and_records_trajectory(self):
        s = self._base_scenario(lead_gap=15.0, ego_speed=30.0, lead_speed=10.0)
        r = self.adapter.run_episode(s, seed=101, config={"max_steps": 30})
        self.assertGreater(r.steps, 0)
        self.assertEqual(len(r.trajectory), r.steps)
        self.assertEqual(r.scenario_hash, s.scenario_hash)
        self.assertIn("approximation_warning", r.raw)


if __name__ == "__main__":
    unittest.main()
