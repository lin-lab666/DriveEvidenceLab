"""Integration tests for the CommonRoad adapter (real third-party library).

These tests exercise `commonroad-io` for real; they are skipped when the
optional dependency is absent so the core suite stays installable without it.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.sim import create_adapter, list_adapters

try:
    from driveevidence.sim.commonroad_adapter import (
        build_commonroad_scenario,
        commonroad_version,
        exchange_roundtrip,
    )

    _CR_VERSION = commonroad_version()
    _HAVE_CR = _CR_VERSION is not None
except Exception:  # pragma: no cover - optional dependency
    _HAVE_CR = False
    _CR_VERSION = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(_HAVE_CR, "commonroad-io not installed")
class CommonRoadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = create_adapter("commonroad")

    def _scenario(self, lead_gap=None, ego_y=1.85, ego_v=25.0, lead_v=20.0):
        vehicles = []
        if lead_gap is not None:
            vehicles.append(
                VehicleState(
                    id="lead", x_m=50.0 + lead_gap, y_m=ego_y, v_mps=lead_v, heading_rad=0.0
                )
            )
        return ScenarioIR(
            scenario_id="cr_test",
            road_length_m=500.0,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=40.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=ego_y, v_mps=ego_v, heading_rad=0.0),
            vehicles=vehicles,
        )

    # --- registry / metadata -------------------------------------------------
    def test_registered(self):
        self.assertIn("commonroad", list_adapters())

    def test_version_reports_real_library_version(self):
        self.assertIn("commonroad-io/", self.adapter.version)
        self.assertIn(_CR_VERSION, self.adapter.version)

    def test_capabilities_do_not_overclaim(self):
        caps = self.adapter.capabilities()
        self.assertTrue(caps["commonroad_geometry"])
        self.assertTrue(caps["commonroad_scenario_exchange"])
        # The whole point: this backend must never claim to be a dynamics engine.
        self.assertFalse(caps["independent_dynamics"])
        self.assertFalse(caps["third_party_dynamics_engine"])

    # --- scenario exchange ---------------------------------------------------
    def test_xml_roundtrip_preserves_geometry(self):
        scenario = self._scenario(lead_gap=25.0)
        with tempfile.TemporaryDirectory() as td:
            info = exchange_roundtrip(scenario, td)
            self.assertEqual(info["lanelets_read"], scenario.lanes)
            self.assertEqual(info["obstacles_read"], 1 + len(scenario.vehicles))
            self.assertAlmostEqual(info["ego_position"][0], scenario.ego.x_m, places=6)
            self.assertAlmostEqual(info["ego_position"][1], scenario.ego.y_m, places=6)
            self.assertAlmostEqual(info["ego_velocity"], scenario.ego.v_mps, places=6)
            self.assertAlmostEqual(info["ego_length"], scenario.ego.length_m, places=6)
            self.assertAlmostEqual(info["ego_width"], scenario.ego.width_m, places=6)
            self.assertGreater(info["xml_bytes"], 1000)

    def test_built_scenario_validates_under_commonroad(self):
        scenario = self._scenario(lead_gap=15.0)
        cr_scenario = build_commonroad_scenario(scenario)
        self.assertEqual(len(cr_scenario.lanelet_network.lanelets), scenario.lanes)
        self.assertEqual(len(cr_scenario.dynamic_obstacles), 1 + len(scenario.vehicles))
        self.assertAlmostEqual(float(cr_scenario.dt), 0.1)

    # --- shared dynamics -----------------------------------------------------
    def test_trajectory_matches_builtin(self):
        """Same kinematics: any category difference must come from the judge."""
        scenario = self._scenario(lead_gap=30.0)
        config = {"max_steps": 40}
        builtin = create_adapter("builtin")
        a = builtin.run_episode(scenario, 0, "safe_follow", config)
        b = self.adapter.run_episode(scenario, 0, "safe_follow", config)
        self.assertEqual(len(a.trajectory), len(b.trajectory))
        for sa, sb in zip(a.trajectory, b.trajectory):
            self.assertAlmostEqual(sa.x, sb.x, places=9)
            self.assertAlmostEqual(sa.y, sb.y, places=9)
            self.assertAlmostEqual(sa.v, sb.v, places=9)

    # --- taxonomy agreement --------------------------------------------------
    def test_both_backends_report_collision(self):
        # Lead vehicle only 25 m ahead from the start; ego closing at 5 m/s must
        # rear-end it well within 80 steps.
        scenario = self._scenario(lead_gap=25.0)
        config = {"max_steps": 80}
        builtin = create_adapter("builtin")
        a = builtin.run_episode(scenario, 0, "constant_speed", config)
        b = self.adapter.run_episode(scenario, 0, "constant_speed", config)
        self.assertEqual(a.failure_category.value, "collision")
        self.assertEqual(b.failure_category.value, "collision")

    def test_both_backends_report_off_road(self):
        # Ego straddles the lower road boundary: its footprint leaves lanelet 0.
        scenario = self._scenario(ego_y=0.3, ego_v=10.0)
        config = {"max_steps": 20}
        builtin = create_adapter("builtin")
        a = builtin.run_episode(scenario, 0, "safe_follow", config)
        b = self.adapter.run_episode(scenario, 0, "safe_follow", config)
        self.assertEqual(a.failure_category.value, "off_road")
        self.assertEqual(b.failure_category.value, "off_road")

    def test_both_backends_agree_on_clean_cruise(self):
        scenario = self._scenario(ego_y=1.85, ego_v=20.0)
        config = {"max_steps": 30}
        builtin = create_adapter("builtin")
        a = builtin.run_episode(scenario, 0, "safe_follow", config)
        b = self.adapter.run_episode(scenario, 0, "safe_follow", config)
        self.assertEqual(a.failure_category.value, b.failure_category.value)

    def test_invalid_scenario_is_infeasible_not_an_exception(self):
        bad = ScenarioIR(
            scenario_id="bad",
            road_length_m=-1.0,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=0.0, y_m=1.85, v_mps=10.0, heading_rad=0.0),
        )
        result = self.adapter.run_episode(bad, 0, "safe_follow", {})
        self.assertEqual(result.failure_category.value, "infeasible")
        self.assertEqual(result.steps, 0)


@unittest.skipUnless(_HAVE_CR, "commonroad-io not installed")
class CommonRoadInteropArtifactTests(unittest.TestCase):
    """The committed interop report must match the recorded adapter versions."""

    def test_committed_report_has_no_exchange_failures(self):
        path = PROJECT_ROOT / "runs" / "formal_experiment_v2p1" / "commonroad_interop.json"
        if not path.exists():
            self.skipTest("interop report not generated in this checkout")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["exchange_failures"], [])
        self.assertEqual(data["trajectory_mismatches"], [])
        self.assertGreater(data["n_candidates"], 0)


if __name__ == "__main__":
    unittest.main()
