"""Guard the publication gate: a PLACEHOLDER repository URL must block a real
release commit, while a preview build (no --commit) stays allowed.

This is the behaviour the CI relies on and that an independent review flagged as
previously broken (the blocker was written into PUBLIC_RELEASE.md but did not
affect the exit code).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD = REPO_ROOT / "scripts" / "build_public_release.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestPublicationGate(unittest.TestCase):
    def test_preview_build_without_commit_is_allowed(self):
        # Even with a PLACEHOLDER URL, a non-committing preview build must
        # succeed — CI uses it to privacy-scan the copy.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            proc = _run("--out", td, "--force")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_commit_refuses_placeholder_url(self):
        if "PLACEHOLDER" not in PYPROJECT.read_text(encoding="utf-8"):
            self.skipTest("no PLACEHOLDER in pyproject; gate is already satisfied")
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            proc = _run("--out", td, "--force", "--commit")
            self.assertNotEqual(
                proc.returncode,
                0,
                "a --commit build with a PLACEHOLDER URL must fail",
            )
            self.assertIn("PLACEHOLDER", proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
