"""End-to-end CLI smoke tests (real commands, no mocking)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliEndToEndTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        cmd = [PYTHON, "-m", "driveevidence.cli.main"] + list(args)
        return subprocess.run(cmd, cwd=PROJECT_ROOT, env=env,
                              capture_output=True, text=True, check=False)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_cli_")
        self.addCleanup(self._tmp.cleanup)
        self.runs_dir = os.path.join(self._tmp.name, "runs")

    def test_doctor(self):
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DriveEvidenceLab Doctor", r.stdout)
        # Must describe the real situation: a source checkout or an installed
        # package, never a site-packages directory mislabelled as "project_root".
        self.assertTrue(
            "project_root:" in r.stdout or "install mode: installed package" in r.stdout,
            r.stdout,
        )
        self.assertIn("registered adapters:", r.stdout)

    def test_sample(self):
        out = os.path.join(self._tmp.name, "scenario.json")
        r = self._run("sample", "--id", "x", "--out", out)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(out))

    def test_run_and_audit(self):
        run_dir = os.path.join(self.runs_dir, "run1")
        r = self._run(
            "run",
            "--scenario", "examples/scenarios/tailgate_risk.json",
            "--adapter", "builtin",
            "--seed", "42",
            "--run-id", "run1",
            "--out", self.runs_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(run_dir, "ledger.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(run_dir, "episodes", "0001.json")))
        self.assertTrue(os.path.exists(os.path.join(run_dir, "manifest.json")))
        audit = self._run("audit", "--run", run_dir)
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("Ledger integrity: PASS", audit.stdout)
        self.assertIn("Manifest integrity: PASS", audit.stdout)

    def test_search_and_report(self):
        run_dir = os.path.join(self.runs_dir, "search1")
        r = self._run(
            "search",
            "--method", "random",
            "--adapter", "builtin",
            "--budget", "12",
            "--seed", "2000",
            "--run-id", "search1",
            "--out", self.runs_dir,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        audit = self._run("audit", "--run", run_dir)
        self.assertEqual(audit.returncode, 0, audit.stderr)
        report_path = os.path.join(self._tmp.name, "report.md")
        rep = self._run("report", "--run", run_dir, "--out", report_path)
        self.assertEqual(rep.returncode, 0)
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("DriveEvidenceLab Run Report", text)

    def test_replay_consistency(self):
        run_dir = os.path.join(self.runs_dir, "run1")
        self._run(
            "run",
            "--scenario", "examples/scenarios/straight_cruise.json",
            "--adapter", "builtin",
            "--seed", "7",
            "--run-id", "run1",
            "--out", self.runs_dir,
        )
        replay = self._run("replay", "--run", run_dir, "--seq", "1", "--adapter", "builtin")
        self.assertEqual(replay.returncode, 0)
        self.assertIn("Category match:", replay.stdout)


class CliErrorHandlingTests(unittest.TestCase):
    """Bad input must produce a clean message and a non-zero exit, never a traceback."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        env.pop("DRIVEEVIDENCE_DEBUG", None)
        cmd = [PYTHON, "-m", "driveevidence.cli.main"] + list(args)
        return subprocess.run(cmd, cwd=PROJECT_ROOT, env=env,
                              capture_output=True, text=True, check=False)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="del_clierr_")
        self.addCleanup(self._tmp.cleanup)

    def _assert_clean_error(self, result: subprocess.CompletedProcess):
        self.assertNotEqual(result.returncode, 0, "expected a non-zero exit code")
        self.assertNotIn("Traceback (most recent call last)", result.stderr,
                         "user error must not surface a raw traceback")
        self.assertIn("error:", result.stderr)

    def test_audit_missing_run_dir(self):
        missing = os.path.join(self._tmp.name, "does_not_exist")
        self._assert_clean_error(self._run("audit", "--run", missing))
        self.assertIn("run directory not found", self._run("audit", "--run", missing).stderr)

    def test_audit_directory_without_ledger(self):
        empty = os.path.join(self._tmp.name, "empty")
        os.makedirs(empty, exist_ok=True)
        r = self._run("audit", "--run", empty)
        self._assert_clean_error(r)
        self.assertIn("no ledger.jsonl", r.stderr)

    def test_audit_path_is_a_file(self):
        f = os.path.join(self._tmp.name, "a_file.txt")
        Path(f).write_text("not a run", encoding="utf-8")
        self._assert_clean_error(self._run("audit", "--run", f))

    def test_report_missing_run_dir(self):
        missing = os.path.join(self._tmp.name, "nope")
        out = os.path.join(self._tmp.name, "r.md")
        self._assert_clean_error(self._run("report", "--run", missing, "--out", out))

    def test_replay_missing_run_dir(self):
        missing = os.path.join(self._tmp.name, "nope")
        self._assert_clean_error(
            self._run("replay", "--run", missing, "--seq", "1")
        )

    def test_run_missing_scenario_file(self):
        missing = os.path.join(self._tmp.name, "no_scenario.json")
        r = self._run("run", "--scenario", missing, "--out", self._tmp.name)
        self._assert_clean_error(r)

    def test_run_malformed_json_scenario(self):
        bad = os.path.join(self._tmp.name, "bad.json")
        Path(bad).write_text("{ this is not json", encoding="utf-8")
        self._assert_clean_error(self._run("run", "--scenario", bad, "--out", self._tmp.name))

    def test_run_scenario_failing_validation(self):
        bad = os.path.join(self._tmp.name, "invalid.json")
        Path(bad).write_text(
            json.dumps({"scenario_id": "x", "road_length_m": -5.0}), encoding="utf-8"
        )
        self._assert_clean_error(self._run("run", "--scenario", bad, "--out", self._tmp.name))

    def test_debug_env_restores_traceback(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        env["DRIVEEVIDENCE_DEBUG"] = "1"
        missing = os.path.join(self._tmp.name, "nope")
        r = subprocess.run(
            [PYTHON, "-m", "driveevidence.cli.main", "audit", "--run", missing],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Traceback (most recent call last)", r.stderr)


if __name__ == "__main__":
    unittest.main()
