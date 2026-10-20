#!/usr/bin/env python3
"""Holdout confirmation of failure candidates discovered by a search run.

Usage:
    python scripts/confirm_candidates.py runs/demo_random_b32_s2000 builtin 3

For each saved candidate, re-run the same scenario with independent holdout
seeds (starting at 3000 + seq) and report stable failure yield (Wilson CI).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driveevidence.evidence import EpisodeStore
from driveevidence.scenario.ir import ScenarioIR
from driveevidence.sim import create_adapter
from driveevidence.stats.estimators import stable_failure_yield


def main() -> int:
    parser = argparse.ArgumentParser(description="Confirm failure candidates on holdout seeds")
    parser.add_argument("run_dir")
    parser.add_argument("adapter", default="builtin")
    parser.add_argument("--holdout-seeds", type=int, default=3)
    parser.add_argument("--base-seed", type=int, default=3000)
    args = parser.parse_args()

    adapter = create_adapter(args.adapter)
    store = EpisodeStore(args.run_dir)

    confirmed = 0
    nominated = 0
    for seq, scenario, result, extra in store.iter_all():
        if not extra.get("candidate"):
            continue
        nominated += 1
        original_cat = result.failure_category
        stable = True
        for i in range(args.holdout_seeds):
            seed = args.base_seed + seq * 100 + i
            rerun = adapter.run_episode(scenario, seed=seed, planner_name="safe_follow",
                                         config={"max_steps": 80})
            if rerun.failure_category != original_cat:
                stable = False
                break
        if stable:
            confirmed += 1
        print(f"seq={seq:04d} original={original_cat.value} stable={stable}")

    point, ci = stable_failure_yield(confirmed, nominated)
    print(f"\nNominated candidates: {nominated}")
    print(f"Confirmed stable:     {confirmed}")
    print(f"Stable yield:         {point:.3f}")
    print(f"Wilson 95% CI:          [{ci[0]:.3f}, {ci[2]:.3f}]")

    summary_path = os.path.join(args.run_dir, "holdout_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "nominated": nominated,
            "confirmed": confirmed,
            "stable_yield": point,
            "wilson_95_ci": [ci[0], ci[2]],
        }, f, ensure_ascii=False, indent=2)
    print(f"Summary saved to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
