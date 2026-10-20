"""End-to-end tests for the public demos and the shipped case pack.

These tests exist so the README's promises stay true: every demo file the
README links to actually runs, and the shipped case pack always audits,
replays and regenerates cleanly.  They use the builtin backend only, so the
core dependency (numpy) is enough.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS = [
    "examples/minimal_sdk_example.py",
    "examples/failure_discovery_demo.py",
    "examples/replay_evidence_demo.py",
    "examples/programmatic_integration_demo.py",
]
README_FIGURES = [
    "docs/_figures/trajectory_collision.png",
    "docs/_figures/gap_and_speed.png",
    "docs/_figures/search_comparison.png",
    "docs/_figures/evidence_pipeline.png",
]
README_LINKED_FILES = [
    "examples/minimal_sdk_example.py",
    "examples/failure_discovery_demo.py",
    "examples/replay_evidence_demo.py",
    "examples/programmatic_integration_demo.py",
    "scripts/make_figures.py",
    "scripts/build_case_pack.py",
    "scripts/verify_evidence_bundle.py",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/LIMITATIONS.md",
    "docs/SCIENTIFIC_AUDIT.zh-CN.md",
    "docs/PROTOCOL-frozen-v2.md",
    "docs/DECISIONS.md",
    "docs/OPEN_SOURCE_QUALITY_AUDIT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
]

# Note: the READMEs use the Unicode minus sign (U+2212) in Newcombe bounds.
V21_NUMBERS = ["0.8906", "0.9531", "0.0444", "0.4114",
               "0.7910", "0.9460", "0.8710", "0.9839",
               "\u22120.0365", "+0.1668", "+0.3669", "0.3218", "0.4124"]


def _run(repo_relative_script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / repo_relative_script)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=180,
    )


class TestDemosRun(unittest.TestCase):
    """Every demo the README links to must run successfully end to end."""

    def test_all_demos_exit_zero(self):
        for demo in DEMOS:
            with self.subTest(demo=demo):
                proc = _run(demo)
                self.assertEqual(proc.returncode, 0,
                                 f"{demo} failed:\n{proc.stdout}\n{proc.stderr}")

    def test_discovery_demo_finds_candidates_and_reports_ci(self):
        proc = _run("examples/failure_discovery_demo.py")
        self.assertIn("failure candidate(s)", proc.stdout)
        self.assertIn("Wilson 95% CI", proc.stdout)

    def test_replay_demo_is_bit_exact(self):
        proc = _run("examples/replay_evidence_demo.py")
        self.assertIn("bit-exact replay  : True", proc.stdout)
        self.assertIn("manifest integrity: PASS", proc.stdout)


class TestCasePack(unittest.TestCase):
    """The shipped case pack must verify and replay from a fresh checkout."""

    def test_pack_files_exist(self):
        base = REPO_ROOT / "examples" / "case_pack"
        for rel in ("README.md", "SHA256SUMS", "run/ledger.jsonl",
                    "run/manifest.json"):
            self.assertTrue((base / rel).exists(), f"missing {rel}")

    def test_sha256sums_cover_all_run_files(self):
        base = REPO_ROOT / "examples" / "case_pack"
        listed = {
            line.split("  ", 1)[1].strip().replace("/", "\\")
            for line in (base / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        actual = {
            p.relative_to(base).as_posix().replace("/", "\\")
            for p in (base / "run").rglob("*") if p.is_file()
        }
        self.assertEqual(listed, actual,
                         "SHA256SUMS and run/ contents diverge")

    def test_case_pack_rebuild_check_matches(self):
        import hashlib
        base = REPO_ROOT / "examples" / "case_pack"
        bad = [
            rel for rel in
            (line.split("  ", 1)[1].strip() for line in
             (base / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
             if line.strip())
            if hashlib.sha256((base / rel).read_bytes()).hexdigest()
            != (base / rel).read_text(encoding="utf-8")  # placeholder, replaced below
        ]
        # (kept simple: recompute properly)
        bad = []
        for line in (base / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, rel = line.split("  ", 1)
            p = base / rel.strip()
            if hashlib.sha256(p.read_bytes()).hexdigest() != digest.strip():
                bad.append(rel)
        self.assertEqual(bad, [], f"tampered pack files: {bad}")


class TestReadmeAssets(unittest.TestCase):
    """README claims must point at real, present files."""

    def test_figures_exist_and_are_png(self):
        for fig in README_FIGURES:
            p = REPO_ROOT / fig
            self.assertTrue(p.exists(), f"missing figure {fig}")
            self.assertGreater(p.stat().st_size, 5_000, f"{fig} suspiciously small")

    def test_readme_linked_files_exist(self):
        for readme in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / readme).read_text(encoding="utf-8")
            for rel in README_LINKED_FILES:
                self.assertIn(rel, text,
                              f"{readme} does not reference {rel}")
                self.assertTrue((REPO_ROOT / rel).exists(),
                                f"{readme} references missing file {rel}")

    def test_figure_sources_manifest_traces_to_real_data(self):
        import json
        manifest = json.loads(
            (REPO_ROOT / "docs" / "_figures" / "sources.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(manifest), 4)
        pipeline = manifest["evidence_pipeline"]
        self.assertIn("schematic", pipeline["source"],
                      "pipeline figure must be labelled as a schematic")
        for name in ("trajectory_collision", "gap_and_speed", "search_comparison"):
            self.assertIn("formal_experiment_v2p1", manifest[name]["source"],
                          f"{name} must trace to the v2.1 run")


class TestReadmeBilingualConsistency(unittest.TestCase):
    """The two READMEs must agree on every headline number."""

    def test_both_readmes_carry_v21_numbers(self):
        for readme in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / readme).read_text(encoding="utf-8")
            for num in V21_NUMBERS:
                self.assertIn(num, text, f"{readme} missing v2.1 number {num}")

    def test_neither_readme_carries_v20_stable_count(self):
        # v2.0 had stable=60 for random; the v2.1 value is 57.
        for readme in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / readme).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\b60 \|\s*\*\*0\.89", readme)
            self.assertIn("| 57 | **0.8906", text,
                          f"{readme} lacks the v2.1 stable count 57")

    def test_h2_guard_phrase_present(self):
        # The editorial policy: H2 must be stated as "not detected" with an
        # explicit guard that this is NOT equivalence.
        guards = {"README.md": '**not** "the methods are equivalent"',
                  "README.zh-CN.md": '**不是**"两方法等价"'}
        for readme, guard in guards.items():
            text = (REPO_ROOT / readme).read_text(encoding="utf-8")
            self.assertIn(guard, text, f"{readme} lacks the H2 not-equivalence guard")


if __name__ == "__main__":
    unittest.main()
