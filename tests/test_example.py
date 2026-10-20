"""Guards that the shipped examples actually run.

The README promises ``python examples/minimal_sdk_example.py`` works; this test
executes it as a subprocess so a future API change cannot silently break the
documented example while unit tests still pass.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "minimal_sdk_example.py"


@unittest.skipUnless(EXAMPLE.exists(), "example script not present")
class TestMinimalSdkExample(unittest.TestCase):
    def test_example_runs_end_to_end(self):
        env = {"PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [sys.executable, str(EXAMPLE)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"example failed:\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        )
        # The example must actually reach its final output line.
        self.assertIn("discovery yield 95% CI:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
