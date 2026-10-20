#!/usr/bin/env python3
"""Cross-check the CommonRoad backend against the builtin backend (Gate D).

What this script actually verifies
----------------------------------
1. **Scenario exchange**: every sampled scenario is mapped to a real
   ``commonroad.scenario.Scenario``, written as CommonRoad XML with
   ``check_validity=True`` (CommonRoad's own validator), read back, and compared
   field by field. Any loss of lanelets/obstacles/pose fails the run.
2. **Trajectory replication**: both backends share the same kinematic rollout,
   so on the same scenario/seed/config they must produce the *same* trajectory.
   We assert this explicitly, which means any category disagreement below is
   attributable to the **judging layer**, not to different dynamics.
3. **Failure taxonomy agreement**: categories from our in-house OBB/off-road
   test are compared with categories from CommonRoad's rectangle occupancies and
   lanelet-union containment. Disagreements are reported, not hidden.

What this script does NOT establish
-----------------------------------
It is not a second independent simulation study: there is no third-party
dynamics engine involved (see ``docs/GATE_D.zh-CN.md``). Do not pool these
numbers with the `builtin` protocol results.

Usage:
    PYTHONPATH=src python scripts/verify_commonroad_interop.py \
        [--run runs/formal_experiment_v2p1] [--per-method 40] [--out <path.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driveevidence.scenario.ir import ScenarioIR  # noqa: E402
from driveevidence.sim import create_adapter  # noqa: E402
from driveevidence.sim.commonroad_adapter import (  # noqa: E402
    commonroad_version,
    exchange_roundtrip,
)

MAX_STEPS = 80


def _load_candidates(run_dir: Path, per_method: int) -> List[Dict[str, Any]]:
    """Sample the first ``per_method`` deduplicated candidates per method."""
    base = run_dir / "discovery"
    picked: List[Dict[str, Any]] = []
    for method in ("random", "mutation"):
        seen = set()
        for report in sorted(base.joinpath(method).glob("seed_*/report.json")):
            data = json.loads(report.read_text(encoding="utf-8"))
            for cand in data.get("candidates", []):
                h = cand.get("scenario_hash")
                if h in seen:
                    continue
                seen.add(h)
                picked.append(
                    {
                        "method": method,
                        "seed": int(report.parent.name.split("_")[1]),
                        "scenario_hash": h,
                        "recorded_category": cand.get("failure_category"),
                        "scenario_dict": cand["scenario_dict"],
                    }
                )
                if len([p for p in picked if p["method"] == method]) >= per_method:
                    break
            if len([p for p in picked if p["method"] == method]) >= per_method:
                break
    return picked


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="runs/formal_experiment_v2p1")
    ap.add_argument("--per-method", type=int, default=40)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    version = commonroad_version()
    if not version:
        print("[FAIL] commonroad-io is not installed; `pip install commonroad-io`", file=sys.stderr)
        return 2

    run_dir = Path(args.run)
    if not run_dir.exists():
        print(f"[FAIL] run directory not found: {run_dir}", file=sys.stderr)
        return 2

    builtin = create_adapter("builtin")
    commonroad = create_adapter("commonroad")
    candidates = _load_candidates(run_dir, args.per_method)
    if not candidates:
        print(f"[FAIL] no candidates found under {run_dir}/discovery", file=sys.stderr)
        return 2

    print("CommonRoad interoperability check (Gate D)")
    print("=" * 72)
    print(f"commonroad-io     : {version}")
    print(f"builtin version   : {builtin.version}")
    print(f"commonroad adapter: {commonroad.version}")
    print(f"candidates        : {len(candidates)}")

    exchange_failures: List[str] = []
    trajectory_mismatches: List[Dict[str, Any]] = []
    disagreements: List[Dict[str, Any]] = []
    agreement = Counter()
    recorded_vs_builtin = Counter()

    with tempfile.TemporaryDirectory(prefix="delab_cr_") as tmp:
        for item in candidates:
            scenario = ScenarioIR.from_dict(item["scenario_dict"])

            # 1. exchange through CommonRoad XML, validated by CommonRoad itself
            info = exchange_roundtrip(scenario, tmp)
            if (
                info["lanelets_read"] != info["lanelets_written"]
                or info["obstacles_read"] != info["obstacles_written"]
                or info["ego_position"] is None
                or abs(info["ego_position"][0] - scenario.ego.x_m) > 1e-6
                or abs(info["ego_position"][1] - scenario.ego.y_m) > 1e-6
                or abs(info["ego_velocity"] - scenario.ego.v_mps) > 1e-6
                or abs(info["ego_length"] - scenario.ego.length_m) > 1e-6
                or abs(info["ego_width"] - scenario.ego.width_m) > 1e-6
            ):
                exchange_failures.append(f"{item['method']}/{item['scenario_hash'][:12]}: {info}")

            config = {"max_steps": MAX_STEPS}
            seed = 0
            r_builtin = builtin.run_episode(scenario, seed, "safe_follow", config)
            r_cr = commonroad.run_episode(scenario, seed, "safe_follow", config)

            # 2. same kinematics must yield the same trajectory
            if len(r_builtin.trajectory) != len(r_cr.trajectory) or any(
                abs(a.x - b.x) > 1e-9 or abs(a.y - b.y) > 1e-9 or abs(a.v - b.v) > 1e-9
                for a, b in zip(r_builtin.trajectory, r_cr.trajectory)
            ):
                trajectory_mismatches.append(
                    {
                        "method": item["method"],
                        "scenario_hash": item["scenario_hash"],
                        "builtin_steps": len(r_builtin.trajectory),
                        "commonroad_steps": len(r_cr.trajectory),
                    }
                )

            # 3. taxonomy agreement
            pair = (r_builtin.failure_category.value, r_cr.failure_category.value)
            agreement[pair] += 1
            if pair[0] != pair[1]:
                disagreements.append(
                    {
                        "method": item["method"],
                        "scenario_hash": item["scenario_hash"],
                        "builtin": pair[0],
                        "commonroad": pair[1],
                        "builtin_detail": r_builtin.failure_detail,
                        "commonroad_detail": r_cr.failure_detail,
                    }
                )
            recorded_vs_builtin[(item["recorded_category"], pair[0])] += 1

    total = len(candidates)
    agree = sum(n for (a, b), n in agreement.items() if a == b)
    rate = agree / total if total else 0.0

    print()
    print(f"exchange failures     : {len(exchange_failures)} / {total}")
    print(f"trajectory mismatches : {len(trajectory_mismatches)} / {total}")
    print(f"category agreement    : {agree} / {total}  ({rate:.1%})")
    print()
    print("agreement matrix (builtin -> commonroad):")
    for (a, b), n in sorted(agreement.items(), key=lambda kv: -kv[1]):
        flag = "" if a == b else "   <-- DISAGREEMENT"
        print(f"  {a:<14} -> {b:<14} {n:5d}{flag}")
    if disagreements:
        print()
        print("disagreements (first 10):")
        for d in disagreements[:10]:
            print(
                f"  {d['method']:<8} {d['scenario_hash'][:12]}  "
                f"builtin={d['builtin']}  commonroad={d['commonroad']}"
            )
            print(f"      builtin  : {d['builtin_detail']}")
            print(f"      commonroad: {d['commonroad_detail']}")

    result = {
        "commonroad_io_version": version,
        "builtin_version": builtin.version,
        "commonroad_adapter_version": commonroad.version,
        "run_dir": str(run_dir),
        "max_steps": MAX_STEPS,
        "n_candidates": total,
        "exchange_failures": exchange_failures,
        "trajectory_mismatches": trajectory_mismatches,
        "category_agreement": {f"{a}->{b}": n for (a, b), n in agreement.items()},
        "agreement_rate": rate,
        "disagreements": disagreements,
        "recorded_vs_builtin": {f"{a}->{b}": n for (a, b), n in recorded_vs_builtin.items()},
        "scope": (
            "Cross-check of the failure taxonomy and scenario exchange against the real "
            "commonroad-io library. Dynamics are shared with builtin, so this is not an "
            "independent simulation study and must not be pooled with protocol results."
        ),
    }
    out = Path(args.out) if args.out else run_dir / "commonroad_interop.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print()
    print(f"written to {out}")

    ok = not exchange_failures and not trajectory_mismatches
    print()
    print(f"RESULT: {'PASS' if ok else 'FAIL'} "
          f"(exchange + trajectory replication; taxonomy agreement reported above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
