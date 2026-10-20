#!/usr/bin/env python3
"""Independent scientific-validity audit of DriveEvidenceLab Gate E.

This script deliberately does **not** trust ``summary.json``. It re-derives every
number from the archived raw artifacts and then compares.

It also separates three tiers that are easy to conflate:

* **T1 internal consistency** - do the artifacts agree with each other and with
  a from-scratch recomputation? (This is what a hash chain and a manifest buy.)
* **T2 methodological validity** - do the measurements actually measure what
  the protocol claims? (v1 fails here: its holdout seeds were inert.)
* **T3 external replication** - has an independent party reproduced the
  result? (Currently: no.)

Usage:
    PYTHONPATH=src python scripts/audit_scientific_validity.py
    PYTHONPATH=src python scripts/audit_scientific_validity.py --v2 runs/formal_experiment_v2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from driveevidence.evidence import EpisodeStore, RunLedger, verify_manifest  # noqa: E402
from driveevidence.evidence.replay import replay_episode  # noqa: E402
from driveevidence.scenario.ir import ScenarioIR  # noqa: E402
from driveevidence.scenario.perturb import perturbation_seeds  # noqa: E402
from driveevidence.sim import create_adapter  # noqa: E402
from driveevidence.stats.estimators import (  # noqa: E402
    binomial_tail_p,
    bootstrap_p_value,
    cohens_h,
    fisher_exact_two_sided,
    holm_correction,
    newcombe_diff_ci,
    paired_bootstrap_ci,
    wilson_ci,
)

FAILURE_VALUES = {"collision", "off_road", "near_miss", "rule_violation"}
METHODS = ["random", "mutation"]
FLOAT_TOL = 1e-9


class Audit:
    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def add(self, tier: str, name: str, passed: bool, detail: str, evidence: Any = None) -> None:
        self.checks.append(
            {
                "tier": tier,
                "check": name,
                "status": "PASS" if passed else "FAIL",
                "detail": detail,
                "evidence": evidence,
            }
        )

    def summary(self) -> Dict[str, Any]:
        tiers = {"T1_internal_consistency": [], "T2_methodological_validity": [], "T3_external_replication": []}
        for c in self.checks:
            tiers.setdefault(c["tier"], []).append(c)
        out = {}
        for tier, items in tiers.items():
            passed = sum(1 for i in items if i["status"] == "PASS")
            out[tier] = {
                "passed": passed,
                "failed": len(items) - passed,
                "total": len(items),
                "checks": items,
            }
        return out


def _read_json(p: Path) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _close(a: Any, b: Any, tol: float = 1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


# ---------------------------------------------------------------------------
# A. Protocol integrity
# ---------------------------------------------------------------------------
def audit_protocol(audit: Audit) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # --- v2: reproducible body hash ---
    v2 = _PROJECT_ROOT / "docs/PROTOCOL-frozen-v2.md"
    freeze = _PROJECT_ROOT / "docs/PROTOCOL-v2.freeze.json"
    if v2.exists() and freeze.exists():
        raw = v2.read_bytes()
        body = hashlib.sha256(raw.split(b"<!-- SIGNATURE -->")[0]).hexdigest()
        full = hashlib.sha256(raw).hexdigest()
        rec = _read_json(freeze)
        ok = rec.get("protocol_body_sha256") == body and rec.get("full_file_sha256") == full
        audit.add(
            "T1_internal_consistency",
            "protocol v2 hash reproducible",
            ok,
            "body and full-file SHA-256 recomputed from bytes match the freeze record",
            {"body": body, "full": full},
        )
        out["v2"] = {"body": body, "full": full, "verified": ok}

    # --- v1: does the embedded hash reconcile with anything? ---
    v1 = _PROJECT_ROOT / "docs/PROTOCOL-frozen-v1.md"
    if v1.exists():
        raw = v1.read_bytes()
        full_v1 = hashlib.sha256(raw).hexdigest()
        lines = raw.decode("utf-8").replace("\r\n", "\n").splitlines(keepends=True)
        excl_last = hashlib.sha256(
            "".join(lines[:-1]).encode("utf-8")
        ).hexdigest()
        prefix = raw.decode("utf-8").replace("\r\n", "\n").rsplit("protocol_sha256", 1)[0]
        prefix_hash = hashlib.sha256(prefix.rstrip().encode("utf-8")).hexdigest()
        embedded = None
        for line in raw.decode("utf-8").splitlines():
            if line.strip().startswith("`protocol_sha256"):
                embedded = line.split("=")[-1].strip().strip("`").strip()
        candidates = {
            "full_file": full_v1,
            "exclude_signature_line": excl_last,
            "prefix_rstrip": prefix_hash,
        }
        reconciles = embedded in candidates.values()
        audit.add(
            "T2_methodological_validity",
            "protocol v1 embedded hash reconciles",
            reconciles,
            "embedded value does not equal any reproducible digest of the frozen file; "
            "self-referential embedding is mathematically impossible",
            {"embedded": embedded, "candidates": candidates},
        )
        out["v1"] = {"embedded": embedded, "candidates": candidates, "reconciles": reconciles}

        # Was v1 modified after the commit that introduced it?
        try:
            first = subprocess.check_output(
                ["git", "log", "--diff-filter=A", "--format=%H", "--", "docs/PROTOCOL-frozen-v1.md"],
                cwd=str(_PROJECT_ROOT),
            ).decode().split()
            if first:
                original = subprocess.check_output(
                    ["git", "show", f"{first[-1]}:docs/PROTOCOL-frozen-v1.md"],
                    cwd=str(_PROJECT_ROOT),
                )
                unchanged = hashlib.sha256(original).hexdigest() == full_v1
                audit.add(
                    "T1_internal_consistency",
                    "protocol v1 unmodified since freeze commit",
                    unchanged,
                    f"byte comparison against commit {first[-1][:8]}",
                    {"commit": first[-1]},
                )
                out["v1"]["unmodified_since_commit"] = unchanged
        except (subprocess.CalledProcessError, FileNotFoundError):
            audit.add(
                "T1_internal_consistency",
                "protocol v1 unmodified since freeze commit",
                False,
                "git unavailable; could not verify",
            )

    return out


# ---------------------------------------------------------------------------
# B. v1 degeneracy: prove the holdout seeds were inert
# ---------------------------------------------------------------------------
def audit_v1_degeneracy(audit: Audit, v1_dir: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not v1_dir.exists():
        return out

    adapter = create_adapter("builtin")
    example = _PROJECT_ROOT / "examples/scenarios/tailgate_risk.json"
    if example.exists():
        scen = ScenarioIR.from_dict(_read_json(example))
        sigs = {}
        for seed in (0, 1, 3000, 3001, 3002, 999999):
            r = adapter.run_episode(scen, seed=seed, planner_name="safe_follow", config={"max_steps": 80})
            blob = json.dumps(
                {"t": [[s.t, s.x, s.y, s.v, s.heading] for s in r.trajectory],
                 "cat": r.failure_category.value, "steps": r.steps},
                sort_keys=True,
            )
            sigs[seed] = hashlib.sha256(blob.encode()).hexdigest()[:16]
        distinct = len(set(sigs.values()))
        audit.add(
            "T2_methodological_validity",
            "v1 simulator seed inertness",
            distinct == 1,
            "six different seeds yield the identical trajectory digest, confirming the "
            "adapter never consumes the seed (this is why v1 stability was degenerate)",
            {"digests": sigs, "distinct": distinct},
        )
        out["seed_inert_digests"] = sigs

    # Count how many v1 candidates were bit-identical across their 3 holdout seeds.
    identical = varying = 0
    per_method: Dict[str, Dict[str, int]] = {}
    for m in METHODS:
        base = v1_dir / "holdout" / m
        if not base.exists():
            continue
        n_id = n_var = 0
        for d in sorted(base.glob("cand_*")):
            rec = _read_json(d / "summary.json")
            keys = {
                (
                    c["failure_category"],
                    c["steps"],
                    tuple(sorted((k, round(float(v), 9)) for k, v in c["metrics"].items())),
                )
                for c in rec["confirmations"]
            }
            if len(keys) == 1:
                n_id += 1
            else:
                n_var += 1
        per_method[m] = {"identical": n_id, "varying": n_var}
        identical += n_id
        varying += n_var
    if per_method:
        audit.add(
            "T2_methodological_validity",
            "v1 holdout produced zero variation",
            varying == 0 and identical > 0,
            f"{identical} of {identical + varying} candidates were bit-identical across all "
            "3 holdout seeds; the v1 stability metric therefore carried no information",
            per_method,
        )
    out["holdout_variation"] = per_method
    out["identical"] = identical
    out["varying"] = varying
    return out


# ---------------------------------------------------------------------------
# C. v2 completeness and reproducibility of the selection
# ---------------------------------------------------------------------------
def audit_v2_completeness(audit: Audit, v2_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    discovery_seeds = cfg.get("discovery_seeds") or list(range(2100, 2164))
    budget_per_run = cfg.get("budget_per_run", 64)
    n_test = cfg.get("n_test", 64)
    reps = cfg.get("holdout_reps", 3)
    pool = cfg.get("perturbation_pool") or list(range(4100, 4120))
    sel_seed = cfg.get("selection_seed", 4000)

    # C1: every discovery report present, exactly once
    missing, extra, budget_violations = [], [], []
    nomination_order: Dict[str, List[str]] = {}
    for m in METHODS:
        present = {
            int(p.parent.name.split("_")[1])
            for p in (v2_dir / "discovery" / m).glob("seed_*/report.json")
        }
        missing += [f"{m}:{s}" for s in discovery_seeds if s not in present]
        extra += [f"{m}:{s}" for s in present if s not in discovery_seeds]
        seen, order = set(), []
        for s in discovery_seeds:
            p = v2_dir / "discovery" / m / f"seed_{s}" / "report.json"
            if not p.exists():
                continue
            rep = _read_json(p)
            snap = rep["budget_snapshot"]
            if not (
                snap["launched"] <= budget_per_run
                and snap["completed"] + snap["failed"] + snap["cancelled"] + snap["infeasible"]
                == snap["launched"]
            ):
                budget_violations.append(f"{m}:{s}:{snap}")
            for c in rep["candidates"]:
                if c["scenario_hash"] not in seen:
                    seen.add(c["scenario_hash"])
                    order.append(c["scenario_hash"])
        nomination_order[m] = order

    audit.add(
        "T1_internal_consistency",
        "v2 discovery runs complete",
        not missing and not extra,
        f"expected {len(discovery_seeds)} seeds per method; missing={missing[:5]} extra={extra[:5]}",
        {"missing": len(missing), "extra": len(extra)},
    )
    audit.add(
        "T1_internal_consistency",
        "v2 budget invariant holds",
        not budget_violations,
        f"launched <= {budget_per_run} and launched == completed+failed+cancelled+infeasible "
        "for every run",
        {"violations": budget_violations[:5], "count": len(budget_violations)},
    )

    # C2: selection reproducible from (nomination order, seed 4000)
    sel_file = v2_dir / "selection.json"
    if sel_file.exists() and all(nomination_order.values()):
        recorded = _read_json(sel_file)
        rng = np.random.default_rng(sel_seed)
        rederived: Dict[str, List[str]] = {}
        for m in METHODS:
            order = nomination_order[m]
            n_take = min(n_test, len(order))
            idx = np.sort(rng.choice(len(order), size=n_take, replace=False)) if n_take else []
            rederived[m] = [order[int(i)] for i in idx]
        ok = all(
            rederived[m] == recorded["method"][m]["selected_scenario_hashes"] for m in METHODS
        )
        audit.add(
            "T1_internal_consistency",
            "v2 candidate selection reproducible",
            ok,
            "re-drawing from nomination order with rng(4000) reproduces selection.json exactly "
            "(no cherry-picking, no order bias)",
            {m: len(rederived[m]) for m in METHODS},
        )
        out["selection_reproduced"] = ok

    # C3: holdout completeness, distinct perturbation seeds, and real perturbation
    for m in METHODS:
        dirs = sorted((v2_dir / "holdout" / m).glob("cand_*"))
        n_ok = 0
        dup_hashes = 0
        seed_rule_ok = 0
        perturb_effective = 0
        infeasible = 0
        hashes = set()
        for d in dirs:
            rec = _read_json(d / "summary.json")
            if rec["scenario_hash"] in hashes:
                dup_hashes += 1
            hashes.add(rec["scenario_hash"])
            want = perturbation_seeds(pool, rec["candidate_index"], reps)
            if rec["perturbation_seeds"] == want:
                seed_rule_ok += 1
            if len(set(rec["perturbation_seeds"])) == reps:
                n_ok += 1
            src = _read_json(v2_dir / "discovery" / m / f"seed_{rec['discovery_master_seed']}" / "report.json")
            src_hashes = {c["scenario_hash"] for c in src["candidates"]}
            for c in rec["confirmations"]:
                if c["failure_category"] == "infeasible":
                    infeasible += 1
                elif c["perturbed_scenario_hash"] != rec["scenario_hash"]:
                    perturb_effective += 1
            out.setdefault("source_hash_present", {})[f"{m}:{rec['candidate_index']}"] = (
                rec["scenario_hash"] in src_hashes
            )

        audit.add(
            "T1_internal_consistency",
            f"v2 holdout complete ({m})",
            len(dirs) == n_test and dup_hashes == 0 and infeasible == 0,
            f"{len(dirs)} candidates tested, {dup_hashes} duplicate hashes, {infeasible} infeasible perturbations",
            {"n_candidates": len(dirs), "duplicates": dup_hashes, "infeasible": infeasible},
        )
        audit.add(
            "T1_internal_consistency",
            f"v2 perturbation seed assignment ({m})",
            seed_rule_ok == len(dirs) and n_ok == len(dirs),
            "per-candidate seed rotation matches the pre-registered rule and seeds are distinct",
            {"rule_match": seed_rule_ok, "distinct": n_ok, "total": len(dirs)},
        )
        audit.add(
            "T2_methodological_validity",
            f"v2 perturbation actually changes inputs ({m})",
            perturb_effective == len(dirs) * reps - infeasible,
            f"{perturb_effective} of {len(dirs) * reps - infeasible} confirmations ran on a scenario "
            "whose hash differs from the nominated scenario",
            {"effective": perturb_effective, "trials": len(dirs) * reps},
        )

    # C4: discovery and perturbation seed sets must be disjoint
    audit.add(
        "T1_internal_consistency",
        "seed sets disjoint",
        not (set(discovery_seeds) & set(pool)),
        "discovery seeds and perturbation seeds share no value",
        {"overlap": sorted(set(discovery_seeds) & set(pool))},
    )
    return out


# ---------------------------------------------------------------------------
# D. Independent recomputation
# ---------------------------------------------------------------------------
def recompute_v2(v2_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    discovery_seeds = cfg.get("discovery_seeds") or list(range(2100, 2164))
    boot_b = cfg.get("bootstrap_b", 2000)
    boot_seed = cfg.get("bootstrap_seed", 2026)

    stats: Dict[str, Any] = {}
    per_seed_yields: Dict[str, List[float]] = {}
    for m in METHODS:
        launched = failures = 0
        yields = []
        for s in discovery_seeds:
            rep = _read_json(v2_dir / "discovery" / m / f"seed_{s}" / "report.json")
            snap = rep["budget_snapshot"]
            launched += snap["launched"]
            f = sum(1 for e in rep["episode_summaries"] if e["failure_category"] in FAILURE_VALUES)
            failures += f
            yields.append(f / snap["launched"] if snap["launched"] else 0.0)
        tested = stable = trials = confirmed = 0
        for d in (v2_dir / "holdout" / m).glob("cand_*"):
            rec = _read_json(d / "summary.json")
            tested += 1
            stable += 1 if rec["confirmed_count"] >= 2 else 0
            trials += len(rec["confirmations"])
            confirmed += sum(1 for c in rec["confirmations"] if c["confirmed"])
        p = stable / tested if tested else 0.0
        lo, hi = wilson_ci(stable, tested, 1.96)
        stats[m] = {
            "total_launched": launched,
            "discovery_failures": failures,
            "discovery_yield": failures / launched if launched else 0.0,
            "discovery_yield_wilson_95": wilson_ci(failures, launched, 1.96),
            "tested": tested,
            "stable": stable,
            "stable_yield": p,
            "stable_yield_wilson_95": (lo, p, hi),
            "trials": trials,
            "confirmed_trials": confirmed,
            "trial_rate": confirmed / trials if trials else 0.0,
        }
        per_seed_yields[m] = yields

    diffs = [mm - rr for rr, mm in zip(per_seed_yields["random"], per_seed_yields["mutation"])]
    boot_lo, boot_hi = paired_bootstrap_ci(diffs, n_boot=boot_b, seed=boot_seed, alpha=0.05)
    h3_p = bootstrap_p_value(diffs, n_boot=boot_b, seed=boot_seed)

    r, mu = stats["random"], stats["mutation"]
    h1_lower = r["stable_yield_wilson_95"][0]
    h1_p = binomial_tail_p(r["stable"], r["tested"], 0.1)
    diff, nlo, nhi = newcombe_diff_ci(r["stable"], r["tested"], mu["stable"], mu["tested"], 1.96)
    h2_p = fisher_exact_two_sided(
        mu["stable"], mu["tested"] - mu["stable"], r["stable"], r["tested"] - r["stable"]
    )
    adj = holm_correction([h1_p, h2_p, h3_p])

    return {
        "stats": stats,
        "hypotheses": {
            "H1": {
                "stable": r["stable"],
                "tested": r["tested"],
                "stable_yield": r["stable_yield"],
                "wilson_lower_95": h1_lower,
                "p": h1_p,
                "p_holm": adj[0],
                "supported": h1_lower > 0.1,
            },
            "H2": {
                "diff": diff,
                "newcombe_95_ci": (nlo, nhi),
                "fisher_p": h2_p,
                "p_holm": adj[1],
                "cohens_h": cohens_h(mu["stable_yield"], r["stable_yield"]),
                "supported": nlo > 0 or nhi < 0,
            },
            "H3": {
                "mean_diff": float(np.mean(diffs)),
                "paired_bootstrap_95_ci": (boot_lo, boot_hi),
                "p": h3_p,
                "p_holm": adj[2],
                "supported": boot_lo > 0 or boot_hi < 0,
            },
        },
        "diffs": diffs,
    }


def audit_recomputation(audit: Audit, v2_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    rec = recompute_v2(v2_dir, cfg)
    summary_path = v2_dir / "summary.json"
    if not summary_path.exists():
        audit.add("T1_internal_consistency", "v2 summary present", False, "summary.json missing")
        return rec
    reported = _read_json(summary_path)["statistics"]

    mismatches = []
    for m in METHODS:
        for key in ("total_launched", "discovery_failures", "tested_candidates", "stable_candidates"):
            rep_key = {"tested_candidates": "tested", "stable_candidates": "stable"}.get(key, key)
            if reported[m].get(key) != rec["stats"][m].get(rep_key):
                mismatches.append(f"{m}.{key}: reported={reported[m].get(key)} recomputed={rec['stats'][m].get(rep_key)}")
        if not _close(reported[m]["stable_yield"], rec["stats"][m]["stable_yield"], FLOAT_TOL):
            mismatches.append(f"{m}.stable_yield mismatch")
        if not _close(reported[m]["discovery_yield"], rec["stats"][m]["discovery_yield"], FLOAT_TOL):
            mismatches.append(f"{m}.discovery_yield mismatch")

    audit.add(
        "T1_internal_consistency",
        "v2 statistics independently reproducible",
        not mismatches,
        "every headline count and rate recomputed from raw per-seed reports and holdout "
        "summaries matches summary.json",
        {"mismatches": mismatches[:5]},
    )

    rh = reported["hypotheses"]
    hy = rec["hypotheses"]
    hyp_ok = (
        rh["H1_stability_random"]["supported"] == hy["H1"]["supported"]
        and rh["H2_method_difference"]["supported"] == hy["H2"]["supported"]
        and rh["H3_discovery_yield_replication"]["supported"] == hy["H3"]["supported"]
        and _close(rh["H3_discovery_yield_replication"]["mean_diff"], hy["H3"]["mean_diff"], 1e-6)
        and _close(rh["H2_method_difference"]["fisher_two_sided_p"], hy["H2"]["fisher_p"], 1e-9)
    )
    audit.add(
        "T1_internal_consistency",
        "v2 hypothesis decisions reproducible",
        hyp_ok,
        "H1/H2/H3 support decisions and effect estimates reproduce from raw data",
        {"recomputed": hy},
    )
    return rec


# ---------------------------------------------------------------------------
# E. Evidence integrity
# ---------------------------------------------------------------------------
def audit_integrity(audit: Audit, run_dir: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ledger_path = run_dir / "ledger.jsonl"
    if ledger_path.exists():
        ledger = RunLedger.load(str(run_dir))
        ok, bad = ledger.verify_chain()
        audit.add(
            "T1_internal_consistency",
            "ledger hash chain intact",
            ok,
            f"re-walked every JSONL entry; first bad sequence = {bad}",
            {"first_bad_seq": bad, "entries": len(ledger.entries())},
        )
        out["ledger_ok"] = ok
        out["ledger_entries"] = len(ledger.entries())

    if (run_dir / "manifest.json").exists():
        result = verify_manifest(str(run_dir))
        bad = {k: v for k, v in result.items() if v != "ok"}
        audit.add(
            "T1_internal_consistency",
            "manifest matches files on disk",
            not bad,
            f"{len(result)} files checked; {len(bad)} mismatched",
            {"mismatches": list(bad.items())[:5]},
        )
        out["manifest_mismatches"] = len(bad)

    # Replay a few archived episodes.
    store = EpisodeStore(str(run_dir))
    adapter = create_adapter("builtin")
    seqs = [seq for seq, _, _, _ in store.iter_all()][:5]
    replay_ok, replay_detail = 0, []
    for seq in seqs:
        outcome = replay_episode(str(run_dir), seq, adapter)
        if outcome.category_match and all(abs(v) <= 1e-6 for v in outcome.metric_diffs.values()):
            replay_ok += 1
        else:
            replay_detail.append({"seq": seq, "category_match": outcome.category_match,
                                  "metric_diffs": outcome.metric_diffs})
    if seqs:
        audit.add(
            "T1_internal_consistency",
            "archived episodes replay exactly",
            replay_ok == len(seqs),
            f"{replay_ok}/{len(seqs)} replayed episodes reproduce category and metrics within 1e-6",
            {"failures": replay_detail},
        )
        out["replay"] = {"ok": replay_ok, "total": len(seqs)}
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Independent Gate E scientific-validity audit")
    ap.add_argument("--v1", default="runs/formal_experiment_v1")
    ap.add_argument("--v2", default="runs/formal_experiment_v2")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    v1_dir = _PROJECT_ROOT / args.v1
    v2_dir = _PROJECT_ROOT / args.v2
    out_dir = Path(args.out) if args.out else v2_dir

    audit = Audit()

    protocol_findings = audit_protocol(audit)
    v1_findings = audit_v1_degeneracy(audit, v1_dir)

    cfg: Dict[str, Any] = {}
    summary_path = v2_dir / "summary.json"
    if summary_path.exists():
        s = _read_json(summary_path)
        cfg = {
            **s.get("config", {}),
            "bootstrap_b": s["statistics"]["hypotheses"]["H3_discovery_yield_replication"]["bootstrap_b"],
            "bootstrap_seed": s["statistics"]["hypotheses"]["H3_discovery_yield_replication"]["bootstrap_seed"],
        }

    v2_findings = audit_v2_completeness(audit, v2_dir, cfg)
    recomputed = audit_recomputation(audit, v2_dir, cfg)
    integrity = audit_integrity(audit, v2_dir)

    # T3: external replication is a factual statement, not a check we can pass.
    audit.add(
        "T3_external_replication",
        "independent third-party reproduction",
        False,
        "no external party has reproduced these results; every artifact here was produced by "
        "the same authors, code base and machine",
        {"status": "MISSING"},
    )

    tiers = audit.summary()
    payload = {
        "generated_at": _utc_now(),
        "v1_dir": str(v1_dir.relative_to(_PROJECT_ROOT)) if v1_dir.exists() else None,
        "v2_dir": str(v2_dir.relative_to(_PROJECT_ROOT)),
        "protocol": protocol_findings,
        "v1_degeneracy": v1_findings,
        "v2_completeness": {k: v for k, v in v2_findings.items() if k != "source_hash_present"},
        "recomputed": {
            "stats": recomputed["stats"],
            "hypotheses": recomputed["hypotheses"],
        },
        "integrity": integrity,
        "tiers": tiers,
    }
    out_path = out_dir / "audit.json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True, default=str)

    print("=" * 72)
    print("DriveEvidenceLab scientific-validity audit")
    print("=" * 72)
    for tier, info in tiers.items():
        print(f"\n{tier}: {info['passed']}/{info['total']} passed, {info['failed']} failed")
        for c in info["checks"]:
            mark = "PASS" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['check']}")
            print(f"         {c['detail']}")
    print(f"\naudit written to {out_path.relative_to(_PROJECT_ROOT)}")
    failed_t1 = tiers["T1_internal_consistency"]["failed"]
    failed_t2 = tiers["T2_methodological_validity"]["failed"]
    print(f"\nT1 failures={failed_t1}  T2 failures={failed_t2}  T3=not available")
    return 0 if failed_t1 == 0 else 1


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
