"""Demo 2 — Failure discovery with the Python SDK.

Runs a real falsification search (MutationSearch) against the builtin
kinematic simulator with a **fixed, deterministic seed**, so the demo always
produces the same result on every machine.  If the budget is exhausted
without any failure being found, the demo says so explicitly instead of
failing — zero candidates is a legitimate outcome of falsification.

This is a *teaching demo* with a small budget; it is not a formal
statistical experiment (see docs/LIMITATIONS.md for the real protocol).

Run from anywhere once the package is installed:

    python examples/failure_discovery_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from driveevidence.scenario import ScenarioIR
from driveevidence.search import Budget, MutationSearch
from driveevidence.sim import create_adapter, list_adapters
from driveevidence.stats import wilson_ci

# Fixed seed chosen because it deterministically yields failures within a
# small budget (22 failures in 32 episodes); chosen *before* publication and
# never tuned afterwards.  For a real experiment use seeds you did not look at.
DEMO_SEED = 2101
DEMO_BUDGET = 32


def main() -> int:
    print("=" * 64)
    print("DriveEvidenceLab — failure discovery demo")
    print("=" * 64)

    # 1. Pick a simulator backend (builtin needs no optional dependencies).
    print(f"registered adapters: {list_adapters()}")
    adapter = create_adapter("builtin")
    print(f"backend: {adapter.name} v{adapter.version}")
    print(f"backend capabilities: {adapter.capabilities()}")

    # 2. Run the falsification search.
    print(f"\nrunning MutationSearch: budget={DEMO_BUDGET} episodes, "
          f"master_seed={DEMO_SEED} (fixed for reproducibility) ...")
    search = MutationSearch()
    report = search.search(adapter=adapter, budget=Budget(max_episodes=DEMO_BUDGET),
                           master_seed=DEMO_SEED)

    launched = report.budget_snapshot.get("launched", report.n_episodes)
    n_candidates = len(report.candidates)
    print(f"\nsearch finished: {n_candidates} failure candidate(s) "
          f"in {launched} episode(s)")

    # 3. Zero candidates is a legitimate outcome — handle it honestly.
    if n_candidates == 0:
        print("\nNo failures found within this budget.  That is a valid result: "
              "either the policy is robust in this scenario family or the budget "
              "was too small.  Try a larger --budget or a different --seed.")
        return 0

    # 4. Summarise the discovered failures by category.
    by_category: dict = {}
    for c in report.candidates:
        by_category[c.failure_category] = by_category.get(c.failure_category, 0) + 1
    print("\ndiscovered failures by category:")
    for cat, n in sorted(by_category.items()):
        print(f"  {cat:<12} {n}")

    # 5. Show the first candidate's structured record.
    first = report.candidates[0]
    print(f"\nfirst candidate:")
    print(f"  scenario_hash : {first.scenario_hash[:32]}...")
    print(f"  category      : {first.failure_category}")
    print(f"  discovery seed: {first.discovery_seed} (round {first.round_idx})")
    print(f"  metrics       : { {k: round(v, 4) for k, v in first.metrics.items()} }")

    # 6. A Wilson 95% confidence interval on the discovery yield.
    lo, hi = wilson_ci(n_candidates, launched)
    print(f"\ndiscovery yield: {n_candidates}/{launched} = {n_candidates / launched:.4f} "
          f"[Wilson 95% CI: {lo:.4f}, {hi:.4f}]")

    print("\nNext step: run `python examples/replay_evidence_demo.py` to see how "
          "this failure would be replayed and audited from archived evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
