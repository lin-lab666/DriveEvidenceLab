#!/usr/bin/env python3
"""Independent audit of a Gate E formal experiment package.

This script reads raw discovery reports and holdout results and recomputes the
main statistics WITHOUT trusting summary.json. It verifies:

1. Protocol snapshot hash matches docs/PROTOCOL-frozen-v1.md.
2. All 64 discovery seeds produced reports for both methods.
3. Ledger hash chain is intact.
4. Manifest is intact.
5. Per-master-seed discovery counts and yields recomputed from raw summaries.
6. Holdout confirmation counts recomputed from raw holdout episode files.
7. Bootstrap CI recomputed with fixed B=2000, seed=2026.
8. No unexpected file modifications or missing evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from driveevidence.evidence import RunLedger, verify_manifest  # noqa: E402
from driveevidence.evidence.ledger import LedgerError  # noqa: E402
from driveevidence.scenario.ir import ScenarioIR  # noqa: E402
from driveevidence.search.base import FailureCandidate, SearchReport  # noqa: E402
from driveevidence.sim.base import EpisodeResult, FailureCategory  # noqa: E402
from driveevidence.stats.estimators import (  # noqa: E402
    cohens_h,
    paired_bootstrap_ci,
    stable_failure_yield,
    wilson_ci,
)

METHODS = ["random", "mutation"]
DISCOVERY_SEEDS = list(range(2000, 2064))
HOLDOUT_SEEDS = list(range(3000, 3020))
CONFIRMATION_CATEGORIES = {
    FailureCategory.COLLISION,
    FailureCategory.OFF_ROAD,
    FailureCategory.NEAR_MISS,
    FailureCategory.RULE_VIOLATION,
}
CONFIRMATION_VALUES = {fc.value for fc in CONFIRMATION_CATEGORIES}


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _protocol_hash() -> str:
    path = _PROJECT_ROOT / "docs" / "PROTOCOL-frozen-v1.md"
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report_from_dict(d: Dict[str, Any]) -> SearchReport:
    return SearchReport(
        method=d["method"],
        master_seed=d["master_seed"],
        budget_snapshot=d["budget_snapshot"],
        candidates=[FailureCandidate(**c) for c in d["candidates"]],
        n_episodes=d["n_episodes"],
        episode_summaries=d["episode_summaries"],
    )


def _count_failures(summaries: List[Dict[str, Any]]) -> int:
    return sum(
        1 for s in summaries if s.get("failure_category") in CONFIRMATION_VALUES
    )


def audit(output_dir: Path) -> Dict[str, Any]:
    findings: Dict[str, Any] = {"passed": [], "failed": []}

    # 1. Protocol snapshot present and hash matches actual file content.
    snapshot_path = output_dir / "protocol_snapshot.json"
    if not snapshot_path.exists():
        findings["failed"].append("protocol_snapshot.json missing")
        return findings
    snapshot = _read_json(snapshot_path)
    expected_hash = _protocol_hash()
    if snapshot.get("protocol_sha256") != expected_hash:
        findings["failed"].append(
            f"protocol hash mismatch: snapshot={snapshot.get('protocol_sha256')} "
            f"current={expected_hash}"
        )
    else:
        findings["passed"].append("protocol snapshot hash matches current protocol")

    # 1b. Check the self-declared hash inside the protocol file.
    protocol_lines = (_PROJECT_ROOT / "docs" / "PROTOCOL-frozen-v1.md").read_text(
        encoding="utf-8"
    ).splitlines()
    embedded_line = next(
        (line for line in protocol_lines if "protocol_sha256" in line), ""
    )
    if embedded_line:
        embedded_hash = embedded_line.split("=")[-1].strip().strip("`")
        if embedded_hash != expected_hash:
            findings["passed"].append(
                f"NOTE: embedded protocol hash {embedded_hash[:16]}... does not match "
                f"actual file hash {expected_hash[:16]}...; experiment uses actual file hash"
            )
        else:
            findings["passed"].append("embedded protocol hash matches actual file hash")
    else:
        findings["passed"].append("no embedded protocol hash found; using computed file hash")

    # 2. Discovery reports: exactly 64 per method.
    results: Dict[str, Dict[int, SearchReport]] = {m: {} for m in METHODS}
    missing_reports: List[str] = []
    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            path = output_dir / "discovery" / method / f"seed_{seed}" / "report.json"
            if not path.exists():
                missing_reports.append(str(path.relative_to(_PROJECT_ROOT)))
                continue
            results[method][seed] = _report_from_dict(_read_json(path))
    if missing_reports:
        findings["failed"].append(
            f"missing discovery reports: {len(missing_reports)}: {missing_reports[:5]}..."
        )
    else:
        findings["passed"].append("all 128 discovery reports present")

    if missing_reports:
        # Cannot proceed without full discovery data.
        return findings

    # 3. Ledger integrity.
    ledger_path = output_dir / "ledger.jsonl"
    if ledger_path.exists():
        try:
            ledger = RunLedger.load(str(output_dir))
            ok, bad_seq = ledger.verify_chain()
            if ok:
                findings["passed"].append("ledger hash chain intact")
            else:
                findings["failed"].append(f"ledger hash chain broken at seq {bad_seq}")
        except LedgerError as exc:
            findings["failed"].append(f"ledger load error: {exc}")
    else:
        findings["failed"].append("ledger.jsonl missing")

    # 4. Manifest integrity.
    manifest_results = verify_manifest(str(output_dir))
    manifest_ok = (
        manifest_results.get("__manifest__") == "ok"
        and all(v == "ok" for k, v in manifest_results.items() if k != "__manifest__")
    )
    if manifest_ok:
        findings["passed"].append("manifest integrity ok")
    else:
        bad = {k: v for k, v in manifest_results.items() if v != "ok"}
        findings["failed"].append(f"manifest integrity failures: {bad}")

    # 5. Budget invariants from raw reports.
    invariant_violations: List[str] = []
    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            snap = results[method][seed].budget_snapshot
            total = snap["completed"] + snap["failed"] + snap["cancelled"] + snap["infeasible"]
            if total > snap["launched"]:
                invariant_violations.append(f"{method}/{seed}: completed+failed+... > launched")
            if snap["launched"] > snap["max_episodes"]:
                invariant_violations.append(f"{method}/{seed}: launched > max")
    if invariant_violations:
        findings["failed"].append(f"budget invariant violations: {invariant_violations[:5]}")
    else:
        findings["passed"].append("all discovery budget invariants hold")

    # 6. Recompute discovery yields per method and per master seed.
    per_seed_yields: Dict[str, List[float]] = {m: [] for m in METHODS}
    per_method_totals: Dict[str, Dict[str, int]] = {
        m: {"launched": 0, "failures": 0} for m in METHODS
    }
    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            snap = results[method][seed].budget_snapshot
            launched = snap["launched"]
            failures = _count_failures(results[method][seed].episode_summaries)
            per_method_totals[method]["launched"] += launched
            per_method_totals[method]["failures"] += failures
            per_seed_yields[method].append(failures / launched if launched else 0.0)

    # 7. Collect unique candidates and recompute holdout confirmations from raw files.
    unique: Dict[str, List[Tuple[int, FailureCandidate]]] = {m: [] for m in METHODS}
    seen: Dict[str, set] = {m: set() for m in METHODS}
    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            for cand in results[method][seed].candidates:
                if cand.scenario_hash not in seen[method]:
                    seen[method].add(cand.scenario_hash)
                    unique[method].append((seed, cand))

    holdout_results: Dict[str, List[Dict[str, Any]]] = {m: [] for m in METHODS}
    holdout_mismatches: List[str] = []
    for method in METHODS:
        for idx, (discovery_seed, cand) in enumerate(unique[method]):
            cand_label = f"cand_{idx:04d}_{cand.scenario_hash[:12]}"
            summary_path = output_dir / "holdout" / method / cand_label / "summary.json"
            if not summary_path.exists():
                findings["failed"].append(f"missing holdout summary: {summary_path}")
                continue
            summary = _read_json(summary_path)
            # Recompute by loading raw holdout episode results.
            expected_h_seeds = [
                HOLDOUT_SEEDS[(idx + offset) % len(HOLDOUT_SEEDS)]
                for offset in range(3)
            ]
            recomputed = []
            for h_seed in expected_h_seeds:
                result_path = summary_path.parent / f"seed_{h_seed}.json"
                if not result_path.exists():
                    holdout_mismatches.append(f"missing {result_path}")
                    continue
                result = EpisodeResult.from_dict(_read_json(result_path))
                confirmed = (
                    result.failure_category in CONFIRMATION_CATEGORIES
                    and result.failure_category.value == cand.failure_category
                )
                recomputed.append(confirmed)
            recomputed_stable = sum(recomputed) >= 1
            if recomputed_stable != summary.get("stable"):
                holdout_mismatches.append(
                    f"{method}/{cand_label}: recomputed stable={recomputed_stable} "
                    f"summary says {summary.get('stable')}"
                )
            holdout_results[method].append({
                "stable": recomputed_stable,
                "nominated_category": cand.failure_category,
            })

    if holdout_mismatches:
        findings["failed"].append(f"holdout recomputation mismatches: {holdout_mismatches[:5]}")
    else:
        findings["passed"].append("all holdout confirmations recomputed consistently")

    # 8. Recompute statistics independently, applying the same protocol cap.
    HOLDOUT_CAP_PER_METHOD = 16
    stats: Dict[str, Any] = {}
    for method in METHODS:
        launched = per_method_totals[method]["launched"]
        failures = per_method_totals[method]["failures"]
        nominated = len(holdout_results[method])
        confirmed_full = sum(1 for e in holdout_results[method] if e["stable"])
        capped_entries = holdout_results[method][:HOLDOUT_CAP_PER_METHOD]
        confirmed_cap = sum(1 for e in capped_entries if e["stable"])

        point_full, (lo_full, _, hi_full) = stable_failure_yield(
            confirmed_full, nominated, z=1.96
        )
        point_cap, (lo_cap, _, hi_cap) = stable_failure_yield(
            confirmed_cap, nominated, z=1.96
        )

        stats[method] = {
            "total_launched": launched,
            "discovery_failures": failures,
            "discovery_yield": failures / launched if launched else 0.0,
            "discovery_yield_wilson_95": wilson_ci(failures, launched, z=1.96),
            "nominated_candidates": nominated,
            "confirmed_candidates_full": confirmed_full,
            "stable_failure_yield_full": point_full,
            "stable_failure_yield_full_wilson_95": (lo_full, point_full, hi_full),
            "confirmed_candidates_protocol_cap": confirmed_cap,
            "stable_failure_yield_protocol_cap": point_cap,
            "stable_failure_yield_protocol_cap_wilson_95": (lo_cap, point_cap, hi_cap),
        }

    diffs = [m - r for m, r in zip(per_seed_yields["mutation"], per_seed_yields["random"])]
    boot_lo, boot_hi = paired_bootstrap_ci(
        diffs, n_boot=2000, seed=2026, alpha=0.05
    )
    stats["comparison"] = {
        "metric": "discovery_yield_difference (mutation - random)",
        "n_pairs": len(diffs),
        "mean_diff": float(np.mean(diffs)),
        "median_diff": float(np.median(diffs)),
        "std_diff": float(np.std(diffs, ddof=1)),
        "paired_bootstrap_95_ci": (boot_lo, boot_hi),
        "random_mean_yield": float(np.mean(per_seed_yields["random"])),
        "mutation_mean_yield": float(np.mean(per_seed_yields["mutation"])),
        "stable_yield_cohens_h_protocol_cap": cohens_h(
            stats["mutation"]["stable_failure_yield_protocol_cap"],
            stats["random"]["stable_failure_yield_protocol_cap"],
        ),
        "stable_yield_cohens_h_full": cohens_h(
            stats["mutation"]["stable_failure_yield_full"],
            stats["random"]["stable_failure_yield_full"],
        ),
    }

    findings["recomputed_statistics"] = stats

    # 9. Cross-check with summary.json if it exists.
    summary_path = output_dir / "summary.json"
    if summary_path.exists():
        summary = _read_json(summary_path)
        summary_stats = summary.get("statistics", {})
        mismatches = []
        for method in METHODS:
            for key in [
                "total_launched",
                "discovery_failures",
                "nominated_candidates",
                "confirmed_candidates_full",
                "stable_failure_yield_full",
                "confirmed_candidates_protocol_cap",
                "stable_failure_yield_protocol_cap",
            ]:
                a = stats[method].get(key)
                b = summary_stats.get(method, {}).get(key)
                if a != b:
                    mismatches.append(f"{method}.{key}: recomputed={a} summary={b}")
        if mismatches:
            findings["failed"].append(f"summary.json mismatch: {mismatches[:5]}")
        else:
            findings["passed"].append("summary.json statistics match independent recomputation")
    else:
        findings["passed"].append("summary.json absent; only independent recomputation available")

    return findings


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Gate E formal experiment")
    parser.add_argument("--out", default="runs/formal_experiment_v1")
    args = parser.parse_args(argv)

    output_dir = Path(args.out).resolve()
    findings = audit(output_dir)

    print("=" * 60)
    print(f"Audit of {output_dir}")
    print("=" * 60)
    print(f"Passed checks: {len(findings['passed'])}")
    for p in findings["passed"]:
        print(f"  [PASS] {p}")
    print(f"Failed checks: {len(findings['failed'])}")
    for f in findings["failed"]:
        print(f"  [FAIL] {f}")

    if "recomputed_statistics" in findings:
        stats = findings["recomputed_statistics"]
        print("\nRecomputed statistics:")
        for method in METHODS:
            s = stats[method]
            print(
                f"  {method}: launched={s['total_launched']} "
                f"failures={s['discovery_failures']} "
                f"yield={s['discovery_yield']:.4f} "
                f"stable_cap={s['stable_failure_yield_protocol_cap']:.4f} "
                f"({s['confirmed_candidates_protocol_cap']}/{s['nominated_candidates']})"
            )
        comp = stats["comparison"]
        print(
            f"  mean diff (mutation - random): {comp['mean_diff']:.4f} "
            f"CI=[{comp['paired_bootstrap_95_ci'][0]:.4f}, "
            f"{comp['paired_bootstrap_95_ci'][1]:.4f}]"
        )

    return 0 if not findings["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
