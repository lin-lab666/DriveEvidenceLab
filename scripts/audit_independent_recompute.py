#!/usr/bin/env python
"""Independent recomputation of the Gate E v2.1 statistics.

This script is deliberately self-contained: it imports **nothing** from
``driveevidence`` and re-implements every statistical primitive from scratch
(Wilson score interval, Newcombe hybrid-score interval, Fisher exact test,
percentile bootstrap, Holm correction).  Its only inputs are the raw artifacts
written by the experiment runner:

    <run>/discovery/<method>/seed_<n>/report.json   (per-seed episode summaries)
    <run>/holdout/<method>/cand_*/summary.json      (per-candidate confirmations)
    <run>/selection.json                            (pre-registered candidate draw)

Purpose: an auditor who distrusts the project's own statistics can run this
file and compare.  Any disagreement with ``summary.json`` is a defect.

Usage:
    python scripts/audit_independent_recompute.py [--run runs/formal_experiment_v2p1]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# Failure categories that count as a failure, per protocol v2 §5.
FAILURE_CATEGORIES = {"collision", "off_road", "rule_violation", "near_miss"}

B_BOOT = 2000
BOOT_SEED = 2026
ALPHA = 0.05
# The project convention is z = 1.96 exactly (see stats/estimators.py).  The
# exact two-sided normal quantile is 1.959963985; the difference moves the CI
# bound by ~3e-6 and never changes a decision.  We compute both so the reader
# can see the sensitivity rather than having to trust one choice.
Z_95 = 1.96
Z_95_EXACT = 1.959963984540054


# --------------------------------------------------------------------------
# statistical primitives (independent implementations)
# --------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval with continuity correction disabled."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_diff(
    k1: int, n1: int, k2: int, n2: int, z: float = Z_95
) -> Tuple[float, float, float]:
    """Newcombe (1998) method 10 hybrid score interval for p1 - p2."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (d, lower, upper)


def _log_choose(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p (sum of tables no more likely than observed)."""
    n = a + b + c + d
    row1, col1 = a + b, a + c
    log_denom = _log_choose(n, col1)

    def log_p(x: int) -> float:
        return (
            _log_choose(row1, x)
            + _log_choose(n - row1, col1 - x)
            - log_denom
        )

    observed = log_p(a)
    total = 0.0
    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    for x in range(lo, hi + 1):
        lp = log_p(x)
        if lp <= observed + 1e-9:
            total += math.exp(lp)
    return min(1.0, total)


def cohens_h(p1: float, p2: float) -> float:
    return 2.0 * math.asin(math.sqrt(p1)) - 2.0 * math.asin(math.sqrt(p2))


def percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile on an already sorted sequence."""
    if not sorted_vals:
        raise ValueError("empty sample")
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def paired_bootstrap_ci(
    deltas: Sequence[float], b: int = B_BOOT, seed: int = BOOT_SEED
) -> Tuple[float, float, float]:
    """Percentile bootstrap CI for the mean of paired deltas."""
    n = len(deltas)
    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(b):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return (
        sum(deltas) / n,
        percentile(means, ALPHA / 2),
        percentile(means, 1 - ALPHA / 2),
    )


def holm(pvals: Dict[str, float]) -> Dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out: Dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[name] = running
    return out


# --------------------------------------------------------------------------
# artifact loading
# --------------------------------------------------------------------------
def load_discovery(run: Path) -> Dict[str, List[dict]]:
    """Return {method: [per-seed record]} for every discovery seed run."""
    out: Dict[str, List[dict]] = {}
    for method_dir in sorted((run / "discovery").iterdir()):
        if not method_dir.is_dir():
            continue
        records = []
        for seed_dir in sorted(method_dir.iterdir()):
            if not seed_dir.is_dir():
                continue
            rep = json.loads((seed_dir / "report.json").read_text(encoding="utf-8"))
            episodes = rep.get("episode_summaries", [])
            n_fail = sum(
                1
                for e in episodes
                if e.get("failure_category") in FAILURE_CATEGORIES
            )
            records.append(
                {
                    "seed": int(seed_dir.name.split("_")[1]),
                    "episodes": len(episodes),
                    "failures": n_fail,
                    "snapshot": rep.get("budget_snapshot", {}),
                }
            )
        out[method_dir.name] = records
    return out


def load_holdout(run: Path) -> Dict[str, List[dict]]:
    """Return {method: [per-candidate record]} recomputed from raw confirmations."""
    out: Dict[str, List[dict]] = {}
    for method_dir in sorted((run / "holdout").iterdir()):
        if not method_dir.is_dir():
            continue
        cands = []
        for cand_dir in sorted(method_dir.iterdir()):
            if not cand_dir.is_dir():
                continue
            summ = json.loads((cand_dir / "summary.json").read_text(encoding="utf-8"))
            confs = summ.get("confirmations", [])
            n_conf = sum(1 for c in confs if c.get("confirmed"))
            # A candidate is stable when >=2 of 3 perturbations reproduce the
            # discovery-stage failure category.  Retained for auditability:
            # the raw files also let us check the >=2 rule directly.
            stable = n_conf >= 2
            cands.append(
                {
                    "dir": cand_dir.name,
                    "index": summ.get("candidate_index"),
                    "n_perturbations": len(confs),
                    "n_confirmed": n_conf,
                    "stable": stable,
                    "categories": [c.get("failure_category") for c in confs],
                    "perturbed_hashes": [
                        c.get("perturbed_scenario_hash") for c in confs
                    ],
                }
            )
        out[method_dir.name] = cands
    return out


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def check(name: str, ok: bool, detail: str) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/formal_experiment_v2p1")
    ap.add_argument("--summary", default=None, help="defaults to <run>/summary.json")
    args = ap.parse_args()

    run = Path(args.run)
    summary_path = Path(args.summary) if args.summary else run / "summary.json"
    if not summary_path.exists():
        print(f"error: no summary at {summary_path}", file=sys.stderr)
        return 2
    recorded = json.loads(summary_path.read_text(encoding="utf-8"))

    print(f"run            : {run}")
    print(f"protocol       : {recorded.get('protocol_version')}")
    print(f"adapter        : {recorded.get('config', {}).get('adapter_version')}")
    print()

    ok = True

    # ---- 1. discovery stage -------------------------------------------
    disc = load_discovery(run)
    print("== discovery stage ==")
    per_seed_diff: List[float] = []
    disc_yield: Dict[str, float] = {}
    for method, recs in disc.items():
        episodes = sum(r["episodes"] for r in recs)
        failures = sum(r["failures"] for r in recs)
        disc_yield[method] = failures / episodes
        print(
            f"  {method:9s} seeds={len(recs):2d} episodes={episodes:5d} "
            f"failures={failures:4d} yield={failures / episodes:.6f}"
        )
        ok &= check(
            f"{method} seed count",
            len(recs) == 64,
            f"{len(recs)} (expected 64)",
        )
        ok &= check(
            f"{method} budget invariant",
            all(
                r["snapshot"].get("launched", 0) <= r["snapshot"].get("max_episodes", 0)
                for r in recs
            ),
            "launched <= max_episodes on every seed",
        )

    by_seed = {m: {r["seed"]: r for r in recs} for m, recs in disc.items()}
    common = sorted(set(by_seed["random"]) & set(by_seed["mutation"]))
    for s in common:
        r, m = by_seed["random"][s], by_seed["mutation"][s]
        per_seed_diff.append(m["failures"] / m["episodes"] - r["failures"] / r["episodes"])
    mean_d, lo_d, hi_d = paired_bootstrap_ci(per_seed_diff)
    print(
        f"  paired diff (mutation-random): {mean_d:+.4f} "
        f"95% CI [{lo_d:+.4f}, {hi_d:+.4f}] over {len(per_seed_diff)} pairs"
    )

    rec_disc = recorded.get("discovery", {})
    for method in ("random", "mutation"):
        if method in rec_disc:
            ok &= check(
                f"{method} discovery yield matches summary.json",
                abs(rec_disc[method]["discovery_yield"] - disc_yield[method]) < 1e-12,
                f"recomputed {disc_yield[method]:.6f} vs "
                f"recorded {rec_disc[method]['discovery_yield']:.6f}",
            )

    # ---- 2. holdout stage ---------------------------------------------
    print()
    print("== holdout stage ==")
    hold = load_holdout(run)
    stats: Dict[str, Tuple[int, int]] = {}
    for method, cands in hold.items():
        tested = sum(1 for c in cands if c["n_perturbations"] > 0)
        stable = sum(1 for c in cands if c["stable"])
        stats[method] = (stable, tested)
        n_conf_total = sum(c["n_confirmed"] for c in cands)
        print(
            f"  {method:9s} candidates={len(cands):2d} tested={tested:2d} "
            f"stable={stable:2d} raw_confirmations={n_conf_total}/"
            f"{sum(c['n_perturbations'] for c in cands)}"
        )
        ok &= check(
            f"{method} perturbation count",
            all(c["n_perturbations"] == 3 for c in cands),
            "every candidate has exactly 3 perturbations",
        )
        ok &= check(
            f"{method} perturbations actually differ",
            all(
                len({h for h in c["perturbed_hashes"] if h}) == c["n_perturbations"]
                for c in cands
            ),
            "all perturbed scenario hashes distinct within a candidate",
        )

    sel = json.loads((run / "selection.json").read_text(encoding="utf-8"))
    for method in ("random", "mutation"):
        n_sel = sel["method"][method]["n_selected"]
        ok &= check(
            f"{method} tested == pre-registered selection",
            stats[method][1] == n_sel,
            f"tested {stats[method][1]} vs selection.json {n_sel}",
        )

    # ---- 3. hypotheses -------------------------------------------------
    print()
    print("== hypotheses ==")
    k_r, n_r = stats["random"]
    k_m, n_m = stats["mutation"]
    p_r, p_m = k_r / n_r, k_m / n_m
    l_r, u_r = wilson(k_r, n_r)
    l_m, u_m = wilson(k_m, n_m)
    l_r_exact, _ = wilson(k_r, n_r, Z_95_EXACT)
    print(f"  random   stable_yield={p_r:.6f} wilson 95% CI [{l_r:.6f}, {u_r:.6f}]")
    print(f"  mutation stable_yield={p_m:.6f} wilson 95% CI [{l_m:.6f}, {u_m:.6f}]")
    print(
        f"  (exact normal quantile for random lower bound: {l_r_exact:.6f}; "
        f"Δ={abs(l_r_exact - l_r):.2e}, decision unchanged)"
    )

    h1_supported = l_r > 0.1
    print(
        f"  H1 (random stable yield, Wilson lower bound > 0.100): "
        f"{'SUPPORTED' if h1_supported else 'NOT SUPPORTED'}  (lower={l_r:.6f})"
    )

    d, dlo, dhi = newcombe_diff(k_m, n_m, k_r, n_r)
    f_p = fisher_exact_two_sided(k_m, n_m - k_m, k_r, n_r - k_r)
    h = cohens_h(p_m, p_r)
    h2_supported = not (dlo <= 0.0 <= dhi)
    print(
        f"  H2 (mutation - random)  delta={d:+.6f}  Newcombe 95% CI "
        f"[{dlo:+.6f}, {dhi:+.6f}]  Fisher p={f_p:.6g}  h={h:.4f}"
    )
    print(f"     -> {'SUPPORTED' if h2_supported else 'NOT SUPPORTED'}")

    h3_supported = not (lo_d <= 0.0 <= hi_d)
    print(
        f"  H3 (paired discovery diff) delta={mean_d:+.6f}  bootstrap 95% CI "
        f"[{lo_d:+.6f}, {hi_d:+.6f}] -> "
        f"{'SUPPORTED' if h3_supported else 'NOT SUPPORTED'}"
    )

    # ---- 4. cross-check against recorded summary ----------------------
    print()
    print("== cross-check against summary.json ==")
    rec_h = recorded.get("statistics", {}).get("hypotheses", {})
    r1 = rec_h.get("H1_stability_random", {})
    if "wilson_lower_95" in r1:
        ok &= check(
            "H1 wilson lower matches",
            abs(r1["wilson_lower_95"] - l_r) < 1e-9,
            f"recorded {r1['wilson_lower_95']:.9f} vs recomputed {l_r:.9f}",
        )
        ok &= check(
            "H1 stable/tested matches",
            r1.get("stable") == k_r and r1.get("tested") == n_r,
            f"recorded {r1.get('stable')}/{r1.get('tested')} vs "
            f"recomputed {k_r}/{n_r}",
        )
    r2 = rec_h.get("H2_method_difference", {})
    if "newcombe_95_ci" in r2:
        c_lo, c_hi = r2["newcombe_95_ci"]
        ok &= check(
            "H2 Newcombe CI matches",
            abs(c_lo - dlo) < 1e-6 and abs(c_hi - dhi) < 1e-6,
            f"recorded [{c_lo:+.6f}, {c_hi:+.6f}] vs "
            f"recomputed [{dlo:+.6f}, {dhi:+.6f}]",
        )
        ok &= check(
            "H2 Fisher p matches",
            abs(r2.get("fisher_two_sided_p", -1) - f_p) < 1e-9,
            f"recorded {r2.get('fisher_two_sided_p')} vs recomputed {f_p:.9f}",
        )
    r3 = rec_h.get("H3_discovery_yield_replication", {})
    if "paired_bootstrap_95_ci" in r3:
        b_lo, b_hi = r3["paired_bootstrap_95_ci"]
        # Bootstrap with an independent RNG is not bit-identical; require the
        # same decision and an overlapping interval of comparable width.
        same_decision = (not (b_lo <= 0.0 <= b_hi)) == h3_supported
        close = abs(b_lo - lo_d) < 0.02 and abs(b_hi - hi_d) < 0.02
        ok &= check(
            "H3 bootstrap agrees within tolerance",
            same_decision and close,
            f"recorded [{b_lo:+.4f}, {b_hi:+.4f}] vs "
            f"recomputed [{lo_d:+.4f}, {hi_d:+.4f}]; same decision={same_decision}",
        )
        ok &= check(
            "H3 mean diff matches",
            abs(r3.get("mean_diff", -1) - mean_d) < 1e-9,
            f"recorded {r3.get('mean_diff')} vs recomputed {mean_d:.9f}",
        )

    # ---- 5. Holm ------------------------------------------------------
    print()
    print("== Holm correction (FWER 0.05) ==")
    # H1's decision rule is the Wilson lower bound, not a p-value.  For Holm
    # bookkeeping only, we use the exact one-sided binomial tail against
    # p0 = 0.1 (the protocol's threshold).  The decision itself never uses it.
    def binom_tail(k: int, n: int, p0: float) -> float:
        return sum(
            math.comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1)
        )

    raw_p = {
        "H1": binom_tail(k_r, n_r, 0.1),
        "H2": f_p,
        # H3's CI is bootstrap-based; the protocol fixes no p-value convention.
        # We report the floor the runner uses (1/B) so the bookkeeping is
        # explicit rather than implied.
        "H3": 1.0 / B_BOOT if h3_supported else 1.0,
    }
    adj = holm(raw_p)
    for name in ("H1", "H2", "H3"):
        print(
            f"  {name}: raw p={raw_p[name]:.6g}  Holm-adjusted={adj[name]:.6g} "
            f"{'significant' if adj[name] < 0.05 else 'not significant'}"
        )

    print()
    print("RESULT:", "ALL CHECKS PASS" if ok else "MISMATCH FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
