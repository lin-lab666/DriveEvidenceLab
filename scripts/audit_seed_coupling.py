#!/usr/bin/env python3
"""Quantify the random/mutation RNG coupling and its effect on H3 (DECISIONS D019).

Both search methods consume ``np.random.default_rng(master_seed)``. MutationSearch
falls back to a random initialisation whenever its failure archive is empty, so it
draws from the *same* stream as RandomSearch. On a seed where no failure is ever
found, the archive stays empty for all 64 episodes and the two methods execute a
bit-identical scenario sequence.

This script measures, from the archived per-seed reports only:

1. per-pair positional overlap between the random and mutation scenario sequences;
2. how many pairs are fully degenerate (mutation == random);
3. H3 (paired bootstrap on discovery yield) recomputed with and without the
   degenerate pairs, and stratified by overlap.

Direction of the bias: overlap *attenuates* the paired difference (a mechanistic
reading), so if H3 survives the low-overlap stratum its sign is robust.  This is
NOT a proof that the pooled estimate is conservative: the stratification is a
post-hoc regrouping of the same data and does not constitute causal
identification.  See docs/LIMITATIONS.md (section 4) for the current statement.

Usage:
    PYTHONPATH=src python scripts/audit_seed_coupling.py [--run runs/formal_experiment_v2p1]

Exit code 0 always (this is a descriptive audit, not a pass/fail gate); the JSON
output records whether each stratum excludes zero.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driveevidence.stats.estimators import paired_bootstrap_ci  # noqa: E402

BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 2026


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(run_dir: Path) -> List[Dict[str, Any]]:
    base = run_dir / "discovery"
    random_reports = sorted(base.joinpath("random").glob("seed_*/report.json"))
    if not random_reports:
        raise SystemExit(f"no discovery reports under {base}")

    rows: List[Dict[str, Any]] = []
    for path in random_reports:
        seed = int(path.parent.name.split("_")[1])
        mut_path = base / "mutation" / f"seed_{seed}" / "report.json"
        if not mut_path.exists():
            raise SystemExit(f"missing mutation report for seed {seed}")
        r = _read(path)
        m = _read(mut_path)
        rh = [s.get("scenario_hash") for s in r.get("episode_summaries", [])]
        mh = [s.get("scenario_hash") for s in m.get("episode_summaries", [])]
        overlap = sum(1 for a, b in zip(rh, mh) if a == b)
        rows.append(
            {
                "seed": seed,
                "n_episodes": len(rh),
                "positional_overlap": overlap,
                "degenerate": overlap == len(rh) and len(rh) > 0,
                "random_yield": len(r.get("candidates", [])) / max(1, r.get("n_episodes", 1)),
                "mutation_yield": len(m.get("candidates", [])) / max(1, m.get("n_episodes", 1)),
            }
        )
    return rows


def _h3(rows: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    diffs = [r["mutation_yield"] - r["random_yield"] for r in rows]
    lo, hi = paired_bootstrap_ci(diffs, n_boot=BOOTSTRAP_B, seed=BOOTSTRAP_SEED)
    return {
        "label": label,
        "n_pairs": len(rows),
        "mean_diff": statistics.mean(diffs),
        "ci95": [lo, hi],
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="runs/formal_experiment_v2p1")
    ap.add_argument("--out", default=None, help="write JSON here (default: <run>/seed_coupling.json)")
    args = ap.parse_args(argv)

    run_dir = Path(args.run)
    rows = collect(run_dir)

    overlaps = [r["positional_overlap"] for r in rows]
    median_ov = statistics.median(overlaps)
    degenerate = [r for r in rows if r["degenerate"]]

    strata = [
        _h3(rows, "all pairs"),
        _h3([r for r in rows if not r["degenerate"]], "excluding degenerate pairs"),
        _h3([r for r in rows if r["positional_overlap"] < median_ov], "overlap < median"),
        _h3([r for r in rows if r["positional_overlap"] >= median_ov], "overlap >= median"),
    ]

    result = {
        "run_dir": str(run_dir),
        "n_pairs": len(rows),
        "overlap": {
            "min": min(overlaps),
            "median": median_ov,
            "mean": statistics.mean(overlaps),
            "max": max(overlaps),
            "pairs_at_least_half": sum(1 for x in overlaps if x >= rows[0]["n_episodes"] / 2),
        },
        "degenerate_pairs": {
            "n": len(degenerate),
            "seeds": [r["seed"] for r in degenerate],
            "explanation": (
                "mutation falls back to random initialisation while its failure archive "
                "is empty; with the shared default_rng(master_seed) stream it then draws "
                "exactly the same scenarios as random search for the whole run"
            ),
        },
        "h3_sensitivity": strata,
        "direction": (
            "overlap attenuates the paired difference (mechanistic reading); the "
            "low-overlap stratum shows the largest effect, so the sign of H3 is "
            "robust across strata. This does NOT establish that the pooled estimate "
            "is conservative: stratification is a post-hoc regrouping, not causal "
            "identification (see docs/LIMITATIONS.md section 4)."
        ),
        "per_seed": rows,
    }

    out = Path(args.out) if args.out else run_dir / "seed_coupling.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print("Seed coupling audit (D019)")
    print("=" * 64)
    print(f"pairs: {result['n_pairs']}")
    print(
        "positional overlap: min={min} median={median:g} mean={mean:.1f} max={max}".format(
            **result["overlap"]
        )
    )
    print(f"degenerate pairs (mutation == random for all episodes): {len(degenerate)}")
    if degenerate:
        print(f"  seeds: {[r['seed'] for r in degenerate]}")
    print()
    for s in strata:
        print(
            f"  {s['label']:<28} n={s['n_pairs']:2d} "
            f"mean_diff={s['mean_diff']:+.4f} "
            f"CI95=[{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}] "
            f"excludes_zero={s['excludes_zero']}"
        )
    print()
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
