"""Documentation/artifact consistency tests.

Motivation (real defect, 2026-10-19): during a late edit the "actual output"
block in ``docs/FINAL_REPORT.zh-CN.md`` was left with ``stable=60`` while the
adjacent yield was updated to the v2.1 value ``0.8906`` (= 57/64), and the H1
Wilson lower bound plus the H2 Newcombe interval were still the v2.0 numbers.
The prose was internally contradictory and nothing caught it, because no test
compared documentation against the frozen artifacts.

These tests make that class of error mechanical: every headline number in the
reports must equal the value recomputed from the raw run directory, and gate
status wording may not regress.

All tests skip cleanly when the run artifacts are absent (e.g. in a wheel
install or a source tarball without ``runs/``).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = REPO_ROOT / "runs" / "formal_experiment_v2p1"
FINAL_REPORT = REPO_ROOT / "docs" / "FINAL_REPORT.zh-CN.md"
AUDIT_REPORT = REPO_ROOT / "docs" / "SCIENTIFIC_AUDIT.zh-CN.md"


def _summary() -> dict:
    return json.loads((RUN_DIR / "summary.json").read_text(encoding="utf-8"))


class TestV21NumbersInDocs(unittest.TestCase):
    """Headline v2.1 numbers must match the raw artifacts, not v2.0."""

    @classmethod
    def setUpClass(cls):
        if not (RUN_DIR / "summary.json").exists():
            raise unittest.SkipTest("formal v2.1 artifacts not present")
        cls.summary = _summary()
        cls.report_text = FINAL_REPORT.read_text(encoding="utf-8")
        cls.audit_text = AUDIT_REPORT.read_text(encoding="utf-8")

    def test_stable_counts_match_artifacts(self):
        h1 = self.summary["statistics"]["hypotheses"]["H1_stability_random"]
        self.assertEqual(h1["stable"], 57, "raw artifact records 57 stable")
        self.assertEqual(h1["tested"], 64)
        # The fraction form is the least ambiguous way to state it.
        self.assertIn(
            "57/64",
            self.report_text,
            "FINAL_REPORT must state the random stable count as 57/64",
        )

    def test_h1_wilson_lower_bound(self):
        h1 = self.summary["statistics"]["hypotheses"]["H1_stability_random"]
        lower = h1["wilson_lower_95"]
        self.assertAlmostEqual(lower, 0.7910, places=4)
        self.assertIn(
            f"{lower:.4f}",
            self.report_text,
            "FINAL_REPORT must quote the recomputed Wilson lower bound",
        )

    def test_h2_newcombe_interval(self):
        h2 = self.summary["statistics"]["hypotheses"]["H2_method_difference"]
        lo, hi = h2["newcombe_95_ci"]
        # Rounded to four decimals as printed in the report.
        self.assertIn(f"{abs(lo):.4f}", self.report_text)
        self.assertIn(f"{hi:.4f}", self.report_text)

    def test_no_v20_numbers_presented_as_v21(self):
        """The v2.0 (builtin/1.0) numbers must never appear in FINAL_REPORT.

        FINAL_REPORT describes v2.1 only; v2.0 belongs to SCIENTIFIC_AUDIT's
        side-by-side comparison, where it is labelled.
        """
        for stale in ("stable=60", "0.0748", "0.1084", "0.8500"):
            self.assertNotIn(
                stale,
                self.report_text,
                f"stale v2.0 value {stale!r} leaked into FINAL_REPORT",
            )

    def test_no_v20_numbers_in_readmes(self):
        """README / README.zh-CN present v2.1 results; the v2.0 ``stable 60``
        must not leak in (real defect 2026-10-20: both READMEs said ``60`` next
        to ``0.8906``, which is 57/64).  The results table's ``stable`` column
        for random must read 57, not the v2.0 count 60."""
        for name in ("README.md", "README.zh-CN.md"):
            path = REPO_ROOT / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            # The results table must not carry the v2.0 count 60 in the stable
            # column for random (which reads "| 64 | 60 |").
            self.assertNotRegex(
                text,
                r"\|\s*64\s*\|\s*60\s*\|",
                f"{name} carries the v2.0 stable count 60 in its results table",
            )

    def test_api_doc_examples_use_v21_numbers(self):
        """docs/API.md uses ``wilson_ci(60, 64)`` and ``newcombe_diff_ci(60, ...)``
        as its worked example — the v2.0 (builtin/1.0) count.  A reader cannot
        tell the example from the published result, so it must use the v2.1
        count 57/64 (real defect found by independent review 2026-10-20)."""
        api_path = REPO_ROOT / "docs" / "API.md"
        if not api_path.exists():
            self.skipTest("API.md not present")
        text = api_path.read_text(encoding="utf-8")
        # The v2.0 count 60 must not appear as a Wilson/Newcombe example input.
        self.assertNotRegex(
            text,
            r"wilson_ci\(60,\s*64\)",
            "API.md example still uses the v2.0 count 60/64",
        )
        self.assertNotRegex(
            text,
            r"newcombe_diff_ci\(60,\s*64",
            "API.md example still uses the v2.0 count 60/64",
        )

    def test_audit_report_quotes_same_interval(self):
        h2 = self.summary["statistics"]["hypotheses"]["H2_method_difference"]
        lo, hi = h2["newcombe_95_ci"]
        self.assertIn(f"{abs(lo):.4f}", self.audit_text)
        self.assertIn(f"{hi:.4f}", self.audit_text)


class TestPerFileTestCounts(unittest.TestCase):
    """The documented per-file test table must sum to the real test count."""

    def test_documented_counts_match_source(self):
        if not FINAL_REPORT.exists():
            self.skipTest("report not present")
        text = FINAL_REPORT.read_text(encoding="utf-8")
        documented = {
            m.group(1): int(m.group(2))
            for m in re.finditer(
                r"^\|\s*`(test_[A-Za-z0-9_]+\.py)`\s*\|\s*(\d+)\s*\|",
                text,
                re.MULTILINE,
            )
        }
        self.assertTrue(documented, "no per-file table found in FINAL_REPORT")

        tests_dir = REPO_ROOT / "tests"
        actual = {}
        for path in sorted(tests_dir.glob("test_*.py")):
            n = len(
                re.findall(r"^\s*def test_\w+", path.read_text(encoding="utf-8"), re.M)
            )
            actual[path.name] = n

        self.assertEqual(
            documented,
            actual,
            "per-file test counts in FINAL_REPORT do not match the test sources",
        )
        self.assertEqual(sum(documented.values()), sum(actual.values()))


class TestGateDWording(unittest.TestCase):
    """Gate D is PARTIAL. No document may launder that into PASS."""

    def _docs(self):
        for path in sorted((REPO_ROOT / "docs").glob("*.md")):
            yield path, path.read_text(encoding="utf-8")
        for name in ("README.md", "README.zh-CN.md", "CHANGELOG.md"):
            path = REPO_ROOT / name
            if path.exists():
                yield path, path.read_text(encoding="utf-8")

    def test_no_gate_d_pass_claim(self):
        # Lines that legitimately mention PASS are those describing the *path*
        # to PASS, or those that explicitly disclaim it.  A bare assertion of
        # "Gate D ... PASS" is what we forbid.
        allowed_markers = (
            "PARTIAL",
            "不是 PASS",
            "非 PASS",
            "不得表述为 PASS",
            "not PASS",
            "要到 PASS",
            "升到 PASS",
            "升级为 PASS",
            "才能升级为 PASS",
            "历史状态",
            # Sentences that forbid the claim rather than make it.
            "写成 PASS",
            "写成PASS",
            "禁止 Gate D",
        )
        offenders = []
        pattern = re.compile(r"Gate[\s-]?D[^。\n]{0,60}?PASS")
        for path, text in self._docs():
            for line in text.splitlines():
                if not pattern.search(line):
                    continue
                if any(marker in line for marker in allowed_markers):
                    continue
                offenders.append(f"{path.name}: {line.strip()}")
        self.assertEqual(
            offenders, [], "Gate D claimed PASS without disclaimer: " + "; ".join(offenders)
        )

    def test_no_stale_not_verified_claim(self):
        stale = []
        for path, text in self._docs():
            if "Gate D（CommonRoad/CARLA）仍未验证" in text:
                stale.append(path.name)
        self.assertEqual(stale, [], f"stale 'Gate D 未验证' wording in {stale}")


if __name__ == "__main__":
    unittest.main()
