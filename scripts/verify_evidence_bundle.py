#!/usr/bin/env python3
"""Verify a shipped evidence bundle without trusting any pre-computed summary.

An outside reviewer should be able to run exactly this file and decide for
themselves whether the archived numbers hold up. It performs:

  1. checksum verification of the bundle archives
  2. extraction to a throw-away temporary directory
  3. ledger hash-chain walk
  4. manifest file-by-file verification
  5. full statistical recomputation from raw per-seed reports
  6. v1 holdout degeneracy recount
  7. a three-tier verdict (internal consistency / methodological validity /
     external replication)

Usage:
    python scripts/verify_evidence_bundle.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

FAILURE_VALUES = {"collision", "off_road", "near_miss", "rule_violation"}
METHODS = ["random", "mutation"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_checksums(evidence_dir: Path) -> Tuple[bool, List[str]]:
    sums = evidence_dir / "SHA256SUMS"
    if not sums.exists():
        return False, [f"missing {sums}"]
    problems: List[str] = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Tolerate both `sha256sum` output styles: "<hex>  <name>" and "<hex> *<name>".
        parts = line.split(None, 1)
        if len(parts) != 2:
            problems.append(f"unparsable line: {line!r}")
            continue
        digest, name = parts[0].strip(), parts[1].strip().lstrip("*").strip()
        target = evidence_dir / name
        if not target.exists():
            problems.append(f"missing file: {name}")
        elif _sha256(target) != digest:
            problems.append(f"checksum mismatch: {name}")
    return not problems, problems


def extract(archive: Path, dest: Path) -> Path:
    with tarfile.open(archive, "r:gz") as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:  # Python < 3.12 has no filter argument
            tf.extractall(dest)
    return dest


def verify_ledger(run_dir: Path) -> Tuple[bool, str]:
    from driveevidence.evidence import RunLedger

    ledger_path = run_dir / "ledger.jsonl"
    if not ledger_path.exists():
        return False, "ledger.jsonl missing"
    ledger = RunLedger.load(str(run_dir))
    ok, bad = ledger.verify_chain()
    return ok, f"{len(ledger.entries())} entries, first_bad_seq={bad}"


def verify_manifest(run_dir: Path) -> Tuple[bool, str]:
    from driveevidence.evidence import verify_manifest as vm

    if not (run_dir / "manifest.json").exists():
        return False, "manifest.json missing"
    result = vm(str(run_dir))
    bad = {k: v for k, v in result.items() if v != "ok"}
    return not bad, f"{len(result)} files, {len(bad)} mismatched"


def recompute(run_dir: Path) -> Dict[str, Any]:
    from driveevidence.stats.estimators import (
        binomial_tail_p,
        bootstrap_p_value,
        cohens_h,
        fisher_exact_two_sided,
        holm_correction,
        newcombe_diff_ci,
        paired_bootstrap_ci,
        wilson_ci,
    )

    summary = _read_json(run_dir / "summary.json")
    cfg = summary["config"]
    seeds = cfg["discovery_seeds"]
    boot_b = 2000
    boot_seed = 2026

    out: Dict[str, Any] = {"methods": {}, "hypotheses": {}}
    per_seed: Dict[str, List[float]] = {}
    for m in METHODS:
        launched = failures = 0
        yields = []
        for s in seeds:
            rep = _read_json(run_dir / "discovery" / m / f"seed_{s}" / "report.json")
            launched += rep["budget_snapshot"]["launched"]
            f = sum(1 for e in rep["episode_summaries"] if e["failure_category"] in FAILURE_VALUES)
            failures += f
            yields.append(f / rep["budget_snapshot"]["launched"] if rep["budget_snapshot"]["launched"] else 0.0)
        tested = stable = 0
        for d in (run_dir / "holdout" / m).glob("cand_*"):
            rec = _read_json(d / "summary.json")
            tested += 1
            stable += 1 if rec["confirmed_count"] >= 2 else 0
        p = stable / tested if tested else 0.0
        lo, hi = wilson_ci(stable, tested, 1.96)
        out["methods"][m] = {
            "launched": launched,
            "failures": failures,
            "discovery_yield": failures / launched if launched else 0.0,
            "tested": tested,
            "stable": stable,
            "stable_yield": p,
            "stable_yield_wilson_95": [lo, hi],
        }
        per_seed[m] = yields

    diffs = [mm - rr for rr, mm in zip(per_seed["random"], per_seed["mutation"])]
    boot_lo, boot_hi = paired_bootstrap_ci(diffs, n_boot=boot_b, seed=boot_seed, alpha=0.05)
    h3_p = bootstrap_p_value(diffs, n_boot=boot_b, seed=boot_seed)

    r, mu = out["methods"]["random"], out["methods"]["mutation"]
    h1_lower = r["stable_yield_wilson_95"][0]
    h1_p = binomial_tail_p(r["stable"], r["tested"], 0.1)
    diff, lo, hi = newcombe_diff_ci(r["stable"], r["tested"], mu["stable"], mu["tested"], 1.96)
    h2_p = fisher_exact_two_sided(
        mu["stable"], mu["tested"] - mu["stable"], r["stable"], r["tested"] - r["stable"]
    )
    adj = holm_correction([h1_p, h2_p, h3_p])

    out["hypotheses"] = {
        "H1": {"wilson_lower": h1_lower, "p_holm": adj[0], "supported": h1_lower > 0.1},
        "H2": {"diff": diff, "ci": [lo, hi], "p_holm": adj[1], "supported": lo > 0 or hi < 0,
               "cohens_h": cohens_h(mu["stable_yield"], r["stable_yield"])},
        "H3": {"mean_diff": sum(diffs) / len(diffs), "ci": [boot_lo, boot_hi],
               "p_holm": adj[2], "supported": boot_lo > 0 or boot_hi < 0},
    }
    return out


def compare_with_recorded(run_dir: Path, recomputed: Dict[str, Any]) -> List[str]:
    recorded = _read_json(run_dir / "summary.json")["statistics"]
    problems: List[str] = []
    for m in METHODS:
        a = recomputed["methods"][m]
        b = recorded[m]
        if a["launched"] != b["total_launched"]:
            problems.append(f"{m}.launched {a['launched']} != {b['total_launched']}")
        if a["stable"] != b["stable_candidates"]:
            problems.append(f"{m}.stable {a['stable']} != {b['stable_candidates']}")
        if abs(a["stable_yield"] - b["stable_yield"]) > 1e-12:
            problems.append(f"{m}.stable_yield drift")
        if abs(a["discovery_yield"] - b["discovery_yield"]) > 1e-12:
            problems.append(f"{m}.discovery_yield drift")
    rh = recorded["hypotheses"]
    if recomputed["hypotheses"]["H1"]["supported"] != rh["H1_stability_random"]["supported"]:
        problems.append("H1 decision drift")
    if recomputed["hypotheses"]["H2"]["supported"] != rh["H2_method_difference"]["supported"]:
        problems.append("H2 decision drift")
    if recomputed["hypotheses"]["H3"]["supported"] != rh["H3_discovery_yield_replication"]["supported"]:
        problems.append("H3 decision drift")
    return problems


def _descend_single_top(root: Path) -> Path:
    """Return ``root`` itself or its single top-level directory (bundle layouts vary)."""
    if (root / "holdout").is_dir():
        return root
    tops = [p for p in root.iterdir() if p.is_dir()]
    if len(tops) == 1:
        return tops[0]
    return root


def recount_v1_degeneracy(v1_root: Path) -> Dict[str, int]:
    v1_root = _descend_single_top(v1_root)
    identical = varying = 0
    for m in METHODS:
        for d in (v1_root / "holdout" / m).glob("cand_*"):
            rec = _read_json(d / "summary.json")
            if len({(c["failure_category"], c["steps"]) for c in rec["confirmations"]}) == 1:
                identical += 1
            else:
                varying += 1
    return {"identical": identical, "varying": varying}


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a DriveEvidenceLab evidence bundle")
    ap.add_argument("--evidence", default="evidence")
    ap.add_argument("--keep", action="store_true", help="keep the extracted directory")
    args = ap.parse_args()

    evidence_dir = _PROJECT_ROOT / args.evidence
    print("=" * 72)
    print("DriveEvidenceLab evidence bundle verification")
    print("=" * 72)

    ok, problems = check_checksums(evidence_dir)
    print(f"\n[T1] checksums: {'PASS' if ok else 'FAIL'}")
    for p in problems:
        print(f"     {p}")
    if not ok:
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="delab_evidence_"))
    try:
        primary_archive = evidence_dir / "gateE-v2p1-full.tar.gz"
        if not primary_archive.exists():
            primary_archive = evidence_dir / "gateE-v2-full.tar.gz"
        if not primary_archive.exists():
            print("[FAIL] no formal-experiment archive found in evidence/")
            return 1
        extracted_root = extract(primary_archive, tmp)
        # The archive contains a single top-level directory; detect it rather
        # than hard-coding the run name.
        tops = [p for p in extracted_root.iterdir() if p.is_dir()]
        if len(tops) != 1:
            print(f"[FAIL] expected exactly one top-level directory, found {len(tops)}")
            return 1
        v2_root = tops[0]

        v1_tmp = Path(tempfile.mkdtemp(prefix="delab_v1_"))
        extract(evidence_dir / "gateE-v1-holdout-summaries.tar.gz", v1_tmp)

        ok, detail = verify_ledger(v2_root)
        print(f"[T1] ledger hash chain: {'PASS' if ok else 'FAIL'} ({detail})")

        ok, detail = verify_manifest(v2_root)
        print(f"[T1] manifest: {'PASS' if ok else 'FAIL'} ({detail})")

        recomputed = recompute(v2_root)
        drift = compare_with_recorded(v2_root, recomputed)
        print(f"[T1] statistics recomputation: {'PASS' if not drift else 'FAIL'}")
        for d in drift:
            print(f"     {d}")

        degeneracy = recount_v1_degeneracy(v1_tmp)
        n_v1 = degeneracy["identical"] + degeneracy["varying"]
        status = "PASS" if n_v1 > 0 else "FAIL"
        print(
            f"[T1] v1 degeneracy recount: {degeneracy['identical']} identical / "
            f"{degeneracy['varying']} varying across 3 holdout seeds  [{status}]"
        )
        if n_v1 == 0:
            # A silent zero would hide a truncated v1 bundle: the recount is the
            # whole point of shipping it, so treat "no candidates found" as a failure.
            print("     the v1 holdout archive contains no candidates; "
                  "the archive is missing data")
            return 1

        print("\nRecomputed results (from raw artifacts only):")
        for m in METHODS:
            a = recomputed["methods"][m]
            print(
                f"  {m:9s} launched={a['launched']:5d} discovery_yield={a['discovery_yield']:.4f} "
                f"tested={a['tested']} stable={a['stable']} stable_yield={a['stable_yield']:.4f} "
                f"[{a['stable_yield_wilson_95'][0]:.4f}, {a['stable_yield_wilson_95'][1]:.4f}]"
            )
        for name, h in recomputed["hypotheses"].items():
            print(f"  {name}: supported={h['supported']}")

        print("\n[T2] methodological validity: requires reading docs/SCIENTIFIC_AUDIT.zh-CN.md")
        print("     - v1 stability was degenerate: the simulator never consumed its seed")
        print("     - v2 uses epsilon-perturbation; verify by inspecting holdout/*/summary.json")
        print("[T3] external replication: NOT AVAILABLE (same authors, code and machine)")

        if args.keep:
            print(f"\nextracted evidence kept at {v2_root.parent}")
        return 0 if not drift and ok else 1
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(v1_tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
