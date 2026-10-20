"""Minimal runnable SDK example for DriveEvidenceLab.

Shows the Python API end to end, without the CLI: load a scenario, run one
episode through a simulator adapter, run a small falsification search, and
compute a Wilson confidence interval on the discovery yield.

Run from the repository root (the package must be installed first,
e.g. ``pip install -e .``):

    python examples/minimal_sdk_example.py

It needs only the core dependency (numpy); no simulator beyond the builtin
kinematic backend is required.
"""

from __future__ import annotations

import json
from pathlib import Path

from driveevidence.scenario import ScenarioIR
from driveevidence.search import Budget, RandomSearch
from driveevidence.sim import create_adapter, list_adapters
from driveevidence.stats import wilson_ci

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    # 1. Load a scenario from the canonical IR JSON.
    scenario_path = REPO_ROOT / "examples" / "scenarios" / "tailgate_risk.json"
    scenario = ScenarioIR.from_dict(json.loads(scenario_path.read_text(encoding="utf-8")))
    print(f"scenario: {scenario.scenario_id} (ir {scenario.ir_version})")

    # 2. Pick a simulator backend.
    print(f"adapters: {list_adapters()}")
    adapter = create_adapter("builtin")
    print(f"adapter: {adapter.name} v{adapter.version}")

    # 3. Run a single episode and read the failure category.
    result = adapter.run_episode(scenario, seed=123, planner_name="safe_follow")
    print(
        f"episode: steps={result.steps} "
        f"category={result.failure_category.value} "
        f"detail={result.failure_detail!r}"
    )

    # 4. Run a small falsification search and count discovered failures.
    search = RandomSearch()
    budget = Budget(max_episodes=32)
    report = search.search(adapter=adapter, budget=budget, master_seed=42)
    n_failures = len(report.candidates)
    n_launched = report.budget_snapshot["launched"]
    print(f"search: {n_failures} failures / {n_launched} episodes")

    # 5. A Wilson 95% confidence interval on the discovery yield.
    lo, hi = wilson_ci(n_failures, n_launched)
    print(f"discovery yield 95% CI: [{lo:.4f}, {hi:.4f}]")


if __name__ == "__main__":
    main()
