"""Tests for seed-derived scenario epsilon-perturbation."""
import json
import unittest

from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.scenario.perturb import (
    DEFAULT_PERTURBATION_BANDS,
    PERTURBATION_SCHEME,
    PerturbationBands,
    perturb_scenario,
    perturbation_seeds,
)


def _base() -> ScenarioIR:
    return ScenarioIR(
        scenario_id="perturb-base",
        road_length_m=500.0,
        lanes=3,
        lane_width_m=3.7,
        speed_limit_mps=33.0,
        ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=25.0, heading_rad=0.0),
        vehicles=[VehicleState(id="v1", x_m=70.0, y_m=1.85, v_mps=15.0, heading_rad=0.0)],
    )


class TestPerturbDeterminism(unittest.TestCase):
    def test_same_seed_same_scenario(self):
        a = perturb_scenario(_base(), seed=1234)
        b = perturb_scenario(_base(), seed=1234)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.scenario_hash, b.scenario_hash)

    def test_different_seed_differs(self):
        a = perturb_scenario(_base(), seed=1234)
        b = perturb_scenario(_base(), seed=1235)
        self.assertNotEqual(a.scenario_hash, b.scenario_hash)

    def test_zero_bands_reproduce_source(self):
        zero = PerturbationBands(0.0, 0.0, 0.0, 0.0, 0.0)
        a = perturb_scenario(_base(), seed=7, bands=zero)
        self.assertEqual(a.ego.to_dict(), _base().ego.to_dict())
        self.assertEqual(a.vehicles[0].to_dict(), _base().vehicles[0].to_dict())

    def test_salt_changes_stream(self):
        a = perturb_scenario(_base(), seed=7, salt=1)
        b = perturb_scenario(_base(), seed=7, salt=2)
        self.assertNotEqual(a.scenario_hash, b.scenario_hash)


class TestPerturbInvariants(unittest.TestCase):
    def test_structure_preserved(self):
        src = _base()
        for seed in range(20):
            out = perturb_scenario(src, seed=seed)
            self.assertEqual(out.lanes, src.lanes)
            self.assertEqual(out.lane_width_m, src.lane_width_m)
            self.assertEqual(out.road_length_m, src.road_length_m)
            self.assertEqual(out.speed_limit_mps, src.speed_limit_mps)
            self.assertEqual([v.id for v in out.vehicles], [v.id for v in src.vehicles])
            self.assertEqual(out.scenario_id, src.scenario_id)

    def test_bands_respected(self):
        src = _base()
        band = PerturbationBands(
            ego_speed_mps=1.0, ego_lateral_m=0.05,
            lead_gap_m=2.0, lead_speed_mps=0.5, min_gap_m=2.0,
        )
        for seed in range(50):
            out = perturb_scenario(src, seed=seed, bands=band)
            self.assertLessEqual(abs(out.ego.v_mps - src.ego.v_mps), 1.0 + 1e-12)
            self.assertLessEqual(abs(out.ego.y_m - src.ego.y_m), 0.05 + 1e-12)
            self.assertLessEqual(abs(out.vehicles[0].v_mps - src.vehicles[0].v_mps), 0.5 + 1e-12)
            gap = out.vehicles[0].x_m - src.ego.x_m
            self.assertLessEqual(abs(gap - (src.vehicles[0].x_m - src.ego.x_m)), 2.0 + 1e-12)

    def test_speeds_non_negative(self):
        src = _base()
        src.ego.v_mps = 0.2
        src.vehicles[0].v_mps = 0.1
        for seed in range(30):
            out = perturb_scenario(src, seed=seed)
            self.assertGreaterEqual(out.ego.v_mps, 0.0)
            self.assertGreaterEqual(out.vehicles[0].v_mps, 0.0)

    def test_no_overlap_floor(self):
        src = ScenarioIR(
            scenario_id="tight",
            road_length_m=500.0, lanes=3, lane_width_m=3.7, speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=25.0, heading_rad=0.0),
            vehicles=[VehicleState(id="v1", x_m=54.6, y_m=1.85, v_mps=15.0, heading_rad=0.0)],
        )
        for seed in range(30):
            out = perturb_scenario(src, seed=seed)
            gap = out.vehicles[0].x_m - out.ego.x_m
            min_allowed = DEFAULT_PERTURBATION_BANDS.min_gap_m + (
                out.ego.length_m + out.vehicles[0].length_m
            ) / 2.0
            self.assertGreaterEqual(gap + 1e-9, min_allowed)

    def test_provenance_recorded(self):
        out = perturb_scenario(_base(), seed=42)
        rec = out.meta["perturbation"]
        self.assertEqual(rec["scheme"], PERTURBATION_SCHEME)
        self.assertEqual(rec["seed"], 42)
        self.assertEqual(rec["source_scenario_hash"], _base().scenario_hash)

    def test_still_valid_ir(self):
        out = perturb_scenario(_base(), seed=3)
        out.validate()  # must not raise

    def test_hash_changes_not_metadata_noise(self):
        """Scenario hash must reflect the jittered state, not just meta."""
        a = perturb_scenario(_base(), seed=1)
        b = perturb_scenario(_base(), seed=2)
        self.assertNotEqual(
            json.dumps(a.ego.to_dict(), sort_keys=True),
            json.dumps(b.ego.to_dict(), sort_keys=True),
        )


class TestPerturbationSeeds(unittest.TestCase):
    def test_rotation(self):
        pool = [10, 11, 12, 13]
        self.assertEqual(perturbation_seeds(pool, 0, 2), [10, 11])
        self.assertEqual(perturbation_seeds(pool, 3, 2), [13, 10])

    def test_rejects_oversized_request(self):
        with self.assertRaises(ValueError):
            perturbation_seeds([1, 2], 0, 3)

    def test_rejects_empty_or_zero(self):
        with self.assertRaises(ValueError):
            perturbation_seeds([], 0, 1)
        with self.assertRaises(ValueError):
            perturbation_seeds([1], 0, 0)

    def test_distinct(self):
        pool = list(range(3000, 3020))
        seeds = perturbation_seeds(pool, 5, 3)
        self.assertEqual(len(set(seeds)), 3)


if __name__ == "__main__":
    unittest.main()
