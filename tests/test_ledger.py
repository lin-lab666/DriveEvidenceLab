"""Tests for evidence ledger, episode store, manifest and replay."""
import json
import os
import tempfile
import unittest

from driveevidence.evidence import (
    EpisodeStore,
    RunLedger,
    build_manifest,
    replay_episode,
    verify_manifest,
)
from driveevidence.scenario.ir import ScenarioIR, VehicleState
from driveevidence.sim.base import (
    EpisodeResult,
    FailureCategory,
    SimulatorAdapter,
    TrajectorySample,
)


class MockAdapter(SimulatorAdapter):
    """Deterministic mock for replay tests."""

    name = "mock_replay"
    version = "mock/1.0"

    def __init__(self, category: FailureCategory = FailureCategory.COLLISION):
        self._category = category

    def capabilities(self):
        return {"collision": True}

    def run_episode(self, scenario, seed, planner_name="default", config=None):
        return EpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario.scenario_hash,
            adapter_name=self.name,
            adapter_version=self.version,
            planner_name=planner_name,
            seed=seed,
            steps=1,
            wall_time_s=0.0,
            terminated=True,
            truncated=False,
            failure_category=self._category,
            failure_detail="mock",
            trajectory=[TrajectorySample(t=0, x=0, y=0, v=0, heading=0)],
            metrics={"k": 1.0},
        )


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_ledger_")
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = os.path.join(self._tmp.name, "run1")

    def test_chain_integrity(self):
        ledger = RunLedger(self.run_dir, "run1", config={"budget": 10})
        for i in range(5):
            ledger.record(RunLedger.EVENT_EPISODE_COMPLETED, {"episode": i})
        ok, bad = ledger.verify_chain()
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_tamper_detection(self):
        ledger = RunLedger(self.run_dir, "run1", config={"budget": 10})
        for i in range(5):
            ledger.record(RunLedger.EVENT_EPISODE_COMPLETED, {"episode": i})

        # Tamper with a payload in the ledger file
        path = ledger.ledger_path
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        obj = json.loads(lines[2])
        obj["payload"]["episode"] = 9999
        lines[2] = json.dumps(obj) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        ok, bad = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertIsNotNone(bad)

    def test_load_existing(self):
        ledger = RunLedger(self.run_dir, "run1", config={"budget": 10})
        ledger.record(RunLedger.EVENT_EPISODE_COMPLETED, {"episode": 0})
        loaded = RunLedger.load(self.run_dir)
        self.assertEqual(loaded.run_id, "run1")
        self.assertEqual(len(loaded.entries()), 2)  # run_started + episode


class EpisodeStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_store_")
        self.addCleanup(self._tmp.cleanup)
        self.store = EpisodeStore(self._tmp.name)
        self.scenario = ScenarioIR(
            scenario_id="s1",
            road_length_m=500,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=0, y_m=1.85, v_mps=10, heading_rad=0),
        )
        self.result = EpisodeResult(
            scenario_id="s1",
            scenario_hash=self.scenario.scenario_hash,
            adapter_name="mock",
            adapter_version="1.0",
            planner_name="default",
            seed=42,
            steps=1,
            wall_time_s=0.1,
            terminated=False,
            truncated=False,
            failure_category=FailureCategory.NONE,
            failure_detail="ok",
            trajectory=[TrajectorySample(t=0, x=0, y=0, v=10, heading=0)],
            metrics={"m": 1.0},
        )

    def test_save_load_roundtrip(self):
        path = self.store.save(self.scenario, self.result, extra={"note": "test"})
        self.assertTrue(os.path.exists(path))
        s, r, e = self.store.load(1)
        self.assertEqual(s.scenario_id, self.scenario.scenario_id)
        self.assertEqual(r.seed, self.result.seed)
        self.assertEqual(e["note"], "test")

    def test_iter_all(self):
        self.store.save(self.scenario, self.result)
        items = list(self.store.iter_all())
        self.assertEqual(len(items), 1)
        seq, s, r, e = items[0]
        self.assertEqual(seq, 1)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_manifest_")
        self.addCleanup(self._tmp.cleanup)

    def test_build_and_verify(self):
        data_path = os.path.join(self._tmp.name, "data.txt")
        with open(data_path, "w") as f:
            f.write("hello")
        build_manifest(self._tmp.name)
        results = verify_manifest(self._tmp.name)
        self.assertEqual(results["__manifest__"], "ok")
        self.assertEqual(results["data.txt"], "ok")

    def test_tamper_detection(self):
        data_path = os.path.join(self._tmp.name, "data.txt")
        with open(data_path, "w") as f:
            f.write("hello")
        build_manifest(self._tmp.name)
        with open(data_path, "w") as f:
            f.write("tampered")
        results = verify_manifest(self._tmp.name)
        self.assertEqual(results["data.txt"], "hash-mismatch")


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_replay_")
        self.addCleanup(self._tmp.cleanup)
        self.store = EpisodeStore(self._tmp.name)
        self.scenario = ScenarioIR(
            scenario_id="s1",
            road_length_m=500,
            lanes=3,
            lane_width_m=3.7,
            speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=0, y_m=1.85, v_mps=10, heading_rad=0),
        )
        self.result = MockAdapter(FailureCategory.COLLISION).run_episode(
            self.scenario, seed=7, planner_name="default"
        )

    def test_replay_match(self):
        self.store.save(self.scenario, self.result)
        outcome = replay_episode(self._tmp.name, 1, MockAdapter(FailureCategory.COLLISION))
        self.assertTrue(outcome.category_match)

    def test_replay_mismatch_reported(self):
        self.store.save(self.scenario, self.result)
        outcome = replay_episode(self._tmp.name, 1, MockAdapter(FailureCategory.NONE))
        self.assertFalse(outcome.category_match)


if __name__ == "__main__":
    unittest.main()


class TestReplayConfigFidelity(unittest.TestCase):
    """Regression tests for the replay-config bug found by the v2 audit.

    A replay must restore dt/max_steps from the archived result. Falling back
    to adapter defaults silently changed the episode (category could still
    match while metrics and step counts diverged).
    """

    def test_replay_kwargs_restores_adapter_config(self):
        from driveevidence.evidence.episode_store import EpisodeStore

        kwargs = EpisodeStore.replay_kwargs(
            {
                "result": {
                    "seed": 7,
                    "planner_name": "safe_follow",
                    "raw": {"dt": 0.1, "max_steps": 80},
                },
                "extra": {},
            }
        )
        self.assertEqual(kwargs["config"]["max_steps"], 80)
        self.assertEqual(kwargs["config"]["dt"], 0.1)

    def test_replay_kwargs_prefers_extra_config(self):
        from driveevidence.evidence.episode_store import EpisodeStore

        kwargs = EpisodeStore.replay_kwargs(
            {
                "result": {"seed": 1, "planner_name": "safe_follow", "raw": {"max_steps": 80}},
                "extra": {"config": {"max_steps": 40}},
            }
        )
        self.assertEqual(kwargs["config"]["max_steps"], 40)

    def test_replay_kwargs_tolerates_missing_raw(self):
        from driveevidence.evidence.episode_store import EpisodeStore

        kwargs = EpisodeStore.replay_kwargs({"result": {"seed": 2}, "extra": {}})
        self.assertEqual(kwargs["config"], {})
        self.assertEqual(kwargs["planner_name"], "default")

    def test_replay_roundtrip_preserves_metrics(self):
        """End-to-end: save -> replay must reproduce metrics within 1e-9."""
        import json
        import tempfile

        from driveevidence.evidence.episode_store import EpisodeStore
        from driveevidence.evidence.replay import replay_episode
        from driveevidence.scenario.ir import ScenarioIR, VehicleState
        from driveevidence.sim import create_adapter

        scen = ScenarioIR(
            scenario_id="replay-fidelity",
            road_length_m=500.0, lanes=3, lane_width_m=3.7, speed_limit_mps=33.0,
            ego=VehicleState(id="ego", x_m=50.0, y_m=1.85, v_mps=25.0, heading_rad=0.0),
            vehicles=[VehicleState(id="v1", x_m=58.0, y_m=1.85, v_mps=5.0, heading_rad=0.0)],
        )
        adapter = create_adapter("builtin")
        result = adapter.run_episode(
            scen, seed=3, planner_name="safe_follow", config={"max_steps": 80}
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = EpisodeStore(tmp)
            store.save(scen, result, extra={})
            outcome = replay_episode(tmp, 1, adapter)
            self.assertTrue(outcome.category_match)
            self.assertEqual(outcome.replayed_result.steps, result.steps)
            for key, diff in outcome.metric_diffs.items():
                self.assertLessEqual(abs(diff), 1e-9, msg=f"metric {key} drifted")
