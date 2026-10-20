#!/usr/bin/env python3
"""Run DriveEvidenceLab Gate E protocol **v2** (corrective replication).

Why this script exists
----------------------
Protocol v1 ran its "independent holdout seeds" against the builtin simulator
by re-executing an identical deterministic scenario: the adapter instantiated
``np.random.default_rng(seed)`` and never consumed it. Every candidate
therefore reproduced with probability 1, and the resulting "stable yield =
100%" carried no information (see ``docs/SCIENTIFIC_AUDIT.zh-CN.md``).

Protocol v2 replaces seed-only replication with a bounded epsilon-perturbation
of the scenario's initial conditions, uses fresh seed sets that were never
touched by v1, and defines the stability denominator as *tested* candidates
rather than *nominated* candidates.

Everything below is fixed before the first v2 episode runs:
``docs/PROTOCOL-frozen-v2.md`` (body hash recorded in
``docs/PROTOCOL-v2.freeze.json``).

Usage
-----
    PYTHONPATH=src python scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2
    PYTHONPATH=src python scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2 --resume
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from driveevidence.evidence import EpisodeStore, RunLedger, build_manifest  # noqa: E402
from driveevidence.scenario.ir import (  # noqa: E402
    ScenarioIR,
    ScenarioValidationError,
)
from driveevidence.scenario.perturb import (  # noqa: E402
    DEFAULT_PERTURBATION_BANDS,
    PERTURBATION_SCHEME,
    perturb_scenario,
    perturbation_seeds,
)
from driveevidence.search.base import Budget, FailureCandidate, SearchReport  # noqa: E402
from driveevidence.search.mutation_search import MutationSearch  # noqa: E402
from driveevidence.search.random_search import RandomSearch  # noqa: E402
from driveevidence.sim import create_adapter  # noqa: E402
from driveevidence.sim.base import FailureCategory  # noqa: E402
from driveevidence.stats.estimators import (  # noqa: E402
    binomial_tail_p,
    bootstrap_p_value,
    cohens_h,
    fisher_exact_two_sided,
    holm_correction,
    newcombe_diff_ci,
    paired_bootstrap_ci,
    stable_failure_yield,
    wilson_ci,
)

# ---------------------------------------------------------------------------
# Frozen protocol v2 parameters
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "v2.0"
PROTOCOL_FILE = "docs/PROTOCOL-frozen-v2.md"
FREEZE_RECORD = "docs/PROTOCOL-v2.freeze.json"

METHODS = ["random", "mutation"]
DISCOVERY_SEEDS = list(range(2100, 2164))   # 64 master seeds (§4)
SELECTION_SEED = 4000                        # §3
PERTURB_POOL = list(range(4100, 4120))       # 20 seeds (§4)
N_TEST = 64                                  # §3
HOLDOUT_REPS = 3                             # §2
STABLE_MIN_CONFIRM = 2                       # §2: >=2 of 3
BUDGET_PER_RUN = 64                          # §4
MAX_STEPS = 80
ADAPTER_NAME = "builtin"
PLANNER_NAME = "safe_follow"

BANDS = DEFAULT_PERTURBATION_BANDS

BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 2026
ALPHA = 0.05
H1_THRESHOLD = 0.1

FAILURE_CATEGORIES = {
    FailureCategory.COLLISION,
    FailureCategory.OFF_ROAD,
    FailureCategory.NEAR_MISS,
    FailureCategory.RULE_VIOLATION,
}
FAILURE_VALUES = {fc.value for fc in FAILURE_CATEGORIES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_episode(adapter: Any, scenario: ScenarioIR, seed: int):
    return adapter.run_episode(
        scenario, seed=seed, planner_name=PLANNER_NAME, config={"max_steps": MAX_STEPS}
    )


def verify_protocol_freeze() -> Dict[str, Any]:
    """Recompute the protocol body hash and compare with the freeze record."""
    proto = _PROJECT_ROOT / PROTOCOL_FILE
    record_path = _PROJECT_ROOT / FREEZE_RECORD
    raw = proto.read_bytes()
    body = raw.split(b"<!-- SIGNATURE -->")[0]
    computed_body = hashlib.sha256(body).hexdigest()
    computed_full = hashlib.sha256(raw).hexdigest()
    record = _read_json(record_path) if record_path.exists() else {}
    ok = (
        record.get("protocol_body_sha256") == computed_body
        and record.get("full_file_sha256") == computed_full
    )
    return {
        "protocol_file": PROTOCOL_FILE,
        "protocol_version": PROTOCOL_VERSION,
        "body_sha256_computed": computed_body,
        "body_sha256_recorded": record.get("protocol_body_sha256"),
        "full_sha256_computed": computed_full,
        "full_sha256_recorded": record.get("full_file_sha256"),
        "freeze_verified": bool(ok),
    }


def _report_to_dict(report: SearchReport) -> Dict[str, Any]:
    return {
        "method": report.method,
        "master_seed": report.master_seed,
        "budget_snapshot": report.budget_snapshot,
        "n_episodes": report.n_episodes,
        "episode_summaries": report.episode_summaries,
        "candidates": [
            {
                "scenario_hash": c.scenario_hash,
                "scenario_dict": c.scenario_dict,
                "discovery_seed": c.discovery_seed,
                "failure_category": c.failure_category,
                "discovery_method": c.discovery_method,
                "round_idx": c.round_idx,
                "metrics": c.metrics,
            }
            for c in report.candidates
        ],
    }


def _report_from_dict(d: Dict[str, Any]) -> SearchReport:
    return SearchReport(
        method=d["method"],
        master_seed=d["master_seed"],
        budget_snapshot=d["budget_snapshot"],
        candidates=[
            FailureCandidate(
                scenario_hash=c["scenario_hash"],
                scenario_dict=c["scenario_dict"],
                discovery_seed=c["discovery_seed"],
                failure_category=c["failure_category"],
                discovery_method=c["discovery_method"],
                round_idx=c["round_idx"],
                metrics=c["metrics"],
            )
            for c in d["candidates"]
        ],
        n_episodes=d["n_episodes"],
        episode_summaries=d["episode_summaries"],
    )


def _count_failures(summaries: List[Dict[str, Any]]) -> int:
    return sum(1 for s in summaries if s.get("failure_category") in FAILURE_VALUES)


# ---------------------------------------------------------------------------
# Discovery phase
# ---------------------------------------------------------------------------
def run_discovery(
    output_dir: Path, adapter: Any, ledger: RunLedger, resume: bool
) -> Dict[str, Dict[int, SearchReport]]:
    results: Dict[str, Dict[int, SearchReport]] = {m: {} for m in METHODS}
    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            report_path = output_dir / "discovery" / method / f"seed_{seed}" / "report.json"
            if resume and report_path.exists():
                report = _report_from_dict(_read_json(report_path))
            else:
                search = RandomSearch(max_steps=MAX_STEPS) if method == "random" else MutationSearch(
                    max_steps=MAX_STEPS
                )
                budget = Budget(max_episodes=BUDGET_PER_RUN)
                report = search.search(adapter, budget, master_seed=seed)
                _write_json(report_path, _report_to_dict(report))
                ledger.record(
                    "discovery_run",
                    {
                        "phase": "discovery",
                        "method": method,
                        "master_seed": seed,
                        "report_file": str(report_path.relative_to(output_dir)),
                        "budget": report.budget_snapshot,
                        "n_candidates": len(report.candidates),
                        "n_failures": _count_failures(report.episode_summaries),
                    },
                )
            results[method][seed] = report
    return results


# ---------------------------------------------------------------------------
# Candidate selection (pre-registered, uniform, no order bias)
# ---------------------------------------------------------------------------
def select_candidates(
    results: Dict[str, Dict[int, SearchReport]], output_dir: Path
) -> Tuple[Dict[str, List[Tuple[int, FailureCandidate]]], Dict[str, Any]]:
    # Deduplicate by scenario_hash, first-seen order (deterministic).
    unique: Dict[str, List[Tuple[int, FailureCandidate]]] = {m: [] for m in METHODS}
    for method in METHODS:
        seen = set()
        for seed in DISCOVERY_SEEDS:
            for cand in results[method][seed].candidates:
                if cand.scenario_hash not in seen:
                    seen.add(cand.scenario_hash)
                    unique[method].append((seed, cand))

    rng = np.random.default_rng(SELECTION_SEED)
    selected: Dict[str, List[Tuple[int, FailureCandidate]]] = {}
    record: Dict[str, Any] = {
        "selection_seed": SELECTION_SEED,
        "n_test_target": N_TEST,
        "method": {},
    }
    for method in METHODS:
        pool = unique[method]
        n_take = min(N_TEST, len(pool))
        if n_take == 0:
            idx = np.array([], dtype=int)
        else:
            idx = np.sort(rng.choice(len(pool), size=n_take, replace=False))
        chosen = [pool[i] for i in idx]
        selected[method] = chosen
        record["method"][method] = {
            "n_nominated": len(pool),
            "n_selected": len(chosen),
            "selected_indices_in_nomination_order": [int(i) for i in idx],
            "selected_scenario_hashes": [c.scenario_hash for _, c in chosen],
        }
    _write_json(output_dir / "selection.json", record)
    return selected, record


# ---------------------------------------------------------------------------
# Holdout phase (epsilon-perturbation)
# ---------------------------------------------------------------------------
def run_holdout(
    output_dir: Path,
    adapter: Any,
    ledger: RunLedger,
    selected: Dict[str, List[Tuple[int, FailureCandidate]]],
    resume: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    holdout: Dict[str, List[Dict[str, Any]]] = {m: [] for m in METHODS}
    store = EpisodeStore(str(output_dir))

    for method in METHODS:
        for idx, (disc_seed, cand) in enumerate(selected[method]):
            seeds = perturbation_seeds(PERTURB_POOL, idx, HOLDOUT_REPS)
            label = f"cand_{idx:04d}_{cand.scenario_hash[:12]}"
            cand_dir = output_dir / "holdout" / method / label
            summary_path = cand_dir / "summary.json"
            if resume and summary_path.exists():
                holdout[method].append(_read_json(summary_path))
                continue

            src = ScenarioIR.from_dict(cand.scenario_dict)
            confirmations: List[Dict[str, Any]] = []
            for pseed in seeds:
                run_path = cand_dir / f"perturb_{pseed}.json"
                if resume and run_path.exists():
                    rec = _read_json(run_path)
                else:
                    pert = perturb_scenario(src, seed=pseed, bands=BANDS)
                    try:
                        pert.validate()
                    except ScenarioValidationError as exc:
                        rec = {
                            "perturbation_seed": pseed,
                            "perturbed_scenario_hash": pert.scenario_hash,
                            "failure_category": FailureCategory.INFEASIBLE.value,
                            "confirmed": False,
                            "steps": 0,
                            "metrics": {},
                            "infeasible_reason": str(exc),
                            "perturbation": {
                                "ego_v_mps": pert.ego.v_mps,
                                "ego_y_m": pert.ego.y_m,
                                "lead_gap_m": (
                                    pert.vehicles[0].x_m - pert.ego.x_m
                                    if pert.vehicles
                                    else None
                                ),
                                "lead_v_mps": (
                                    pert.vehicles[0].v_mps if pert.vehicles else None
                                ),
                            },
                        }
                        _write_json(run_path, rec)
                    else:
                        result = _run_episode(adapter, pert, pseed)
                        rec = {
                            "perturbation_seed": pseed,
                            "perturbed_scenario_hash": pert.scenario_hash,
                            "failure_category": result.failure_category.value,
                            "confirmed": (
                                result.failure_category.value == cand.failure_category
                            ),
                            "steps": result.steps,
                            "metrics": dict(result.metrics),
                            "perturbation": {
                                "ego_v_mps": pert.ego.v_mps,
                                "ego_y_m": pert.ego.y_m,
                                "lead_gap_m": (
                                    pert.vehicles[0].x_m - pert.ego.x_m
                                    if pert.vehicles
                                    else None
                                ),
                                "lead_v_mps": (
                                    pert.vehicles[0].v_mps if pert.vehicles else None
                                ),
                            },
                        }
                        _write_json(run_path, rec)
                confirmations.append(rec)

            confirmed_count = sum(1 for c in confirmations if c["confirmed"])
            stable = confirmed_count >= STABLE_MIN_CONFIRM
            entry = {
                "method": method,
                "candidate_index": idx,
                "scenario_hash": cand.scenario_hash,
                "discovery_master_seed": disc_seed,
                "discovery_seed": cand.discovery_seed,
                "nominated_category": cand.failure_category,
                "perturbation_scheme": PERTURBATION_SCHEME,
                "perturbation_bands": BANDS.to_dict(),
                "perturbation_seeds": seeds,
                "confirmations": confirmations,
                "confirmed_count": confirmed_count,
                "n_tested": len(confirmations),
                "stable": stable,
            }
            _write_json(summary_path, entry)
            holdout[method].append(entry)

            # Archive one perturbed episode for replay audit.
            replay_rec = confirmations[0]
            if replay_rec["failure_category"] != FailureCategory.INFEASIBLE.value:
                pert = perturb_scenario(src, seed=replay_rec["perturbation_seed"], bands=BANDS)
                result = _run_episode(adapter, pert, replay_rec["perturbation_seed"])
                store.save(
                    pert,
                    result,
                    extra={
                        "method": method,
                        "candidate_index": idx,
                        "protocol": PROTOCOL_VERSION,
                        "holdout": True,
                        "stable": stable,
                    },
                )

            ledger.record(
                "holdout_candidate",
                {
                    "protocol": PROTOCOL_VERSION,
                    "phase": "holdout",
                    "method": method,
                    "candidate_index": idx,
                    "scenario_hash": cand.scenario_hash,
                    "perturbation_scheme": PERTURBATION_SCHEME,
                    "perturbation_seeds": seeds,
                    "confirmed_count": confirmed_count,
                    "n_tested": len(confirmations),
                    "stable": stable,
                },
            )
    return holdout


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def compute_statistics(
    results: Dict[str, Dict[int, SearchReport]],
    holdout: Dict[str, List[Dict[str, Any]]],
    selection: Dict[str, Any],
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}

    for method in METHODS:
        launched = completed = infeasible = failed = failures = 0
        for seed in DISCOVERY_SEEDS:
            snap = results[method][seed].budget_snapshot
            launched += snap["launched"]
            completed += snap["completed"]
            infeasible += snap["infeasible"]
            failed += snap["failed"]
            failures += _count_failures(results[method][seed].episode_summaries)

        tested = len(holdout[method])
        stable = sum(1 for e in holdout[method] if e["stable"])
        n_confirmed_checks = sum(e["confirmed_count"] for e in holdout[method])
        n_checks = sum(e["n_tested"] for e in holdout[method])
        point, (lo, _, hi) = stable_failure_yield(stable, tested, z=1.96)

        # Rate per perturbation trial, which is a different (finer) unit.
        trial_rate = n_confirmed_checks / n_checks if n_checks else 0.0
        trial_lo, trial_hi = wilson_ci(n_confirmed_checks, n_checks, z=1.96)

        stats[method] = {
            "n_discovery_runs": len(DISCOVERY_SEEDS),
            "budget_per_run": BUDGET_PER_RUN,
            "total_launched": launched,
            "total_completed": completed,
            "total_infeasible": infeasible,
            "total_failed": failed,
            "discovery_failures": failures,
            "discovery_yield": failures / launched if launched else 0.0,
            "discovery_yield_wilson_95": wilson_ci(failures, launched, z=1.96),
            "nominated_candidates": selection["method"][method]["n_nominated"],
            "tested_candidates": tested,
            "stable_candidates": stable,
            "stable_yield": point,
            "stable_yield_wilson_95": (lo, point, hi),
            "perturbation_trials": n_checks,
            "perturbation_confirmed": n_confirmed_checks,
            "perturbation_trial_rate": trial_rate,
            "perturbation_trial_rate_wilson_95": (trial_lo, trial_hi),
        }

    # H3: paired bootstrap on discovery yield difference per master seed.
    random_yields, mutation_yields = [], []
    for seed in DISCOVERY_SEEDS:
        r = results["random"][seed]
        m = results["mutation"][seed]
        r_launched = r.budget_snapshot["launched"]
        m_launched = m.budget_snapshot["launched"]
        random_yields.append(
            _count_failures(r.episode_summaries) / r_launched if r_launched else 0.0
        )
        mutation_yields.append(
            _count_failures(m.episode_summaries) / m_launched if m_launched else 0.0
        )
    diffs = [m - r for m, r in zip(mutation_yields, random_yields)]
    boot_lo, boot_hi = paired_bootstrap_ci(
        diffs, n_boot=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, alpha=ALPHA
    )
    h3_p = bootstrap_p_value(diffs, n_boot=BOOTSTRAP_B, seed=BOOTSTRAP_SEED)

    # H1: random search only (protocol v1 scope error corrected in v2).
    r_stable = stats["random"]["stable_candidates"]
    r_tested = stats["random"]["tested_candidates"]
    h1_p = binomial_tail_p(r_stable, r_tested, H1_THRESHOLD)
    h1_lower = stats["random"]["stable_yield_wilson_95"][0]

    # H2: mutation vs random stable yield, equal tested denominators.
    m_stable = stats["mutation"]["stable_candidates"]
    m_tested = stats["mutation"]["tested_candidates"]
    diff, lo, hi = newcombe_diff_ci(r_stable, r_tested, m_stable, m_tested, z=1.96)
    h2_p = fisher_exact_two_sided(
        m_stable, m_tested - m_stable, r_stable, r_tested - r_stable
    )
    h2_h = cohens_h(
        stats["mutation"]["stable_yield"], stats["random"]["stable_yield"]
    )

    adjusted = holm_correction([h1_p, h2_p, h3_p])
    stats["hypotheses"] = {
        "H1_stability_random": {
            "definition": "Wilson 95% lower bound of stable_yield(random) > 0.1",
            "stable": r_stable,
            "tested": r_tested,
            "stable_yield": stats["random"]["stable_yield"],
            "wilson_lower_95": h1_lower,
            "threshold": H1_THRESHOLD,
            "p_value_one_sided_binomial": h1_p,
            "p_value_holm": adjusted[0],
            "supported": bool(h1_lower > H1_THRESHOLD),
        },
        "H2_method_difference": {
            "definition": "Newcombe 95% CI of stable_yield(mutation) - stable_yield(random) excludes 0",
            "diff": diff,
            "newcombe_95_ci": (lo, hi),
            "fisher_two_sided_p": h2_p,
            "p_value_holm": adjusted[1],
            "cohens_h": h2_h,
            "supported": bool(lo > 0 or hi < 0),
        },
        "H3_discovery_yield_replication": {
            "definition": "paired bootstrap 95% CI of discovery_yield diff excludes 0",
            "n_pairs": len(diffs),
            "mean_diff": float(np.mean(diffs)),
            "median_diff": float(np.median(diffs)),
            "std_diff": float(np.std(diffs, ddof=1)),
            "paired_bootstrap_95_ci": (boot_lo, boot_hi),
            "bootstrap_p_two_sided": h3_p,
            "p_value_holm": adjusted[2],
            "bootstrap_b": BOOTSTRAP_B,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "supported": bool(boot_lo > 0 or boot_hi < 0),
        },
        "family_size": 3,
        "correction": "Holm (FWER 0.05)",
    }
    stats["comparison"] = {
        "metric": "stable_yield (tested denominator)",
        "random_stable_yield": stats["random"]["stable_yield"],
        "mutation_stable_yield": stats["mutation"]["stable_yield"],
        "diff_mutation_minus_random": diff,
        "newcombe_95_ci": (lo, hi),
        "cohens_h": h2_h,
    }
    return stats


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def generate_report(output_dir: Path, summary: Dict[str, Any], sel: Dict[str, Any]) -> Path:
    stats = summary["statistics"]
    h = stats["hypotheses"]
    lines = [
        "# DriveEvidenceLab｜Gate E 正式实验报告 v2（缺陷修正复现）",
        "",
        f"- 协议：`{PROTOCOL_FILE}`（{PROTOCOL_VERSION}）",
        f"- 协议正文 SHA-256：`{summary['protocol']['body_sha256_computed']}`",
        f"- 冻结校验：{'PASS' if summary['protocol']['freeze_verified'] else 'FAIL'}",
        f"- 开始：{summary['started_at']}　结束：{summary['finished_at']}",
        f"- 总 wall time：{summary['total_wall_time_s']:.1f}s",
        "",
        "> 本实验的动机是**事后发现 v1 缺陷**。指标与判据在运行前写定、种子全新，",
        "> 但它不属于完全独立的事前预注册，见协议 §7。",
        "",
        "## 1. 执行配置",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 仿真后端 | `{ADAPTER_NAME}` |",
        f"| 规划器 | `{PLANNER_NAME}` |",
        f"| 发现种子 | {DISCOVERY_SEEDS[0]}–{DISCOVERY_SEEDS[-1]}（{len(DISCOVERY_SEEDS)} 个） |",
        f"| 每 seed 预算 | {BUDGET_PER_RUN} episodes |",
        f"| 候选抽样 seed | {SELECTION_SEED} |",
        f"| 扰动种子池 | {PERTURB_POOL[0]}–{PERTURB_POOL[-1]}（{len(PERTURB_POOL)} 个，轮转） |",
        f"| 每候选扰动次数 | {HOLDOUT_REPS} |",
        f"| 稳定判据 | {HOLDOUT_REPS} 次中 ≥{STABLE_MIN_CONFIRM} 次复现同类别 |",
        f"| 扰动方案 | `{PERTURBATION_SCHEME}` {BANDS.to_dict()} |",
        f"| max_steps | {MAX_STEPS} |",
        "",
        "## 2. 预算与记账",
        "",
        "| 方法 | 发现 episodes | 提名候选 | 抽样实测 | 稳定 | stable yield [Wilson 95%] | 扰动试验确认率 |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in METHODS:
        s = stats[m]
        lo, _, hi = s["stable_yield_wilson_95"]
        sel_m = sel["method"][m]
        lines.append(
            f"| {m} | {s['total_launched']} | {sel_m['n_nominated']} | {s['tested_candidates']} | "
            f"{s['stable_candidates']} | {s['stable_yield']:.4f} [{lo:.4f}, {hi:.4f}] | "
            f"{s['perturbation_trial_rate']:.4f} "
            f"({s['perturbation_confirmed']}/{s['perturbation_trials']}) |"
        )

    lines += [
        "",
        "> 提名候选数与实测候选数分列，是因为 v1 把二者混在同一个分母里，导致",
        "> 「发现越多、稳定率越低」的假象。v2 的分母只含**实际做过扰动复测**的候选。",
        "",
        "## 3. 假设检验",
        "",
        "| 假设 | 统计量 | 判据 | p | Holm p | 结论 |",
        "|---|---|---|---|---|---|",
    ]
    h1 = h["H1_stability_random"]
    lines.append(
        f"| H1（随机搜索稳定性） | stable yield = {h1['stable_yield']:.4f}，"
        f"Wilson 下界 {h1['wilson_lower_95']:.4f} | 下界 > {h1['threshold']} | "
        f"{h1['p_value_one_sided_binomial']:.3e} | {h1['p_value_holm']:.3e} | "
        f"{'支持' if h1['supported'] else '不支持'} |"
    )
    h2 = h["H2_method_difference"]
    lines.append(
        f"| H2（方法差异） | Δ = {h2['diff']:.4f}，Newcombe [{h2['newcombe_95_ci'][0]:.4f}, "
        f"{h2['newcombe_95_ci'][1]:.4f}] | CI 不含 0 | {h2['fisher_two_sided_p']:.3e} | "
        f"{h2['p_value_holm']:.3e} | {'支持' if h2['supported'] else '不支持'} |"
    )
    h3 = h["H3_discovery_yield_replication"]
    lines.append(
        f"| H3（发现率复现） | Δ = {h3['mean_diff']:.4f}，bootstrap "
        f"[{h3['paired_bootstrap_95_ci'][0]:.4f}, {h3['paired_bootstrap_95_ci'][1]:.4f}] | "
        f"CI 不含 0 | {h3['bootstrap_p_two_sided']:.3e} | {h3['p_value_holm']:.3e} | "
        f"{'支持' if h3['supported'] else '不支持'} |"
    )
    lines += [
        "",
        f"效应量 Cohen's h（H2）= {h2['cohens_h']:.4f}。多重比较：Holm，族大小 3，FWER 0.05。",
        "",
        "## 4. 与 v1 的差异（为什么数字不可直接对比）",
        "",
        "| 维度 | v1 | v2 |",
        "|---|---|---|",
        "| holdout 种子语义 | seed 传给仿真器但**未被使用** → 逐位相同重跑 | seed 驱动初始条件 ε-扰动 → 真正不同输入 |",
        "| 稳定判据 | 3 次中 ≥1 次 | 3 次中 ≥2 次 |",
        "| 分母 | 全部提名数 | 实测候选数 |",
        "| 候选选择 | 首个 16 个（顺序偏差） | 预注册均匀随机抽 64 个 |",
        "| 种子集 | 2000–2063 / 3000–3019 | 2100–2163 / 4100–4119（全新） |",
        "| 协议哈希 | 内嵌自指哈希，不可核验 | 正文哈希，可一条命令复现 |",
        "",
        "## 5. 结论边界（强制）",
        "",
        "- 适用范围仅限 `builtin` 运动学仿真器 + `safe_follow` + 直道 3 车道场景族。",
        "- 不推断真实道路安全；不跨仿真器合并；不外推到其他规划器。",
        "- 高 stable yield 只表示「该失效对协议规定的 ε 扰动稳健」，不等于「系统性缺陷」或「现实世界失效」。",
        "- 无外部独立团队复现。内部审计通过 ≠ 结论已被独立验证。",
        "",
        "## 6. 产物索引",
        "",
        "- `selection.json`：预注册候选抽样记录",
        "- `discovery/<method>/seed_*/report.json`：每个 master seed 的完整搜索报告",
        "- `holdout/<method>/cand_*/summary.json`：每个候选的扰动复测明细",
        "- `episodes/*.json`：可重放的场景+结果归档",
        "- `ledger.jsonl`：SHA-256 哈希链",
        "- `manifest.json`：全文件完整性清单",
        "- `summary.json`：本报告全部数字的机器可读来源",
    ]
    path = output_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Run Gate E protocol v2")
    ap.add_argument("--out", default="runs/formal_experiment_v2")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    output_dir = _PROJECT_ROOT / args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    protocol = verify_protocol_freeze()
    if not protocol["freeze_verified"]:
        print(
            "FATAL: protocol freeze verification failed\n"
            f"  computed body={protocol['body_sha256_computed']}\n"
            f"  recorded body={protocol['body_sha256_recorded']}\n"
            f"  computed full={protocol['full_sha256_computed']}\n"
            f"  recorded full={protocol['full_sha256_recorded']}",
            file=sys.stderr,
        )
        return 2

    started = _now()
    t0 = time.time()
    adapter = create_adapter(ADAPTER_NAME)
    ledger = RunLedger(
        str(output_dir),
        "gate_e_v2",
        {
            "protocol": PROTOCOL_VERSION,
            "protocol_body_sha256": protocol["body_sha256_computed"],
            "adapter": ADAPTER_NAME,
            "adapter_version": adapter.version,
            "planner": PLANNER_NAME,
            "discovery_seeds": [DISCOVERY_SEEDS[0], DISCOVERY_SEEDS[-1]],
            "selection_seed": SELECTION_SEED,
            "perturbation_pool": [PERTURB_POOL[0], PERTURB_POOL[-1]],
            "perturbation_bands": BANDS.to_dict(),
            "budget_per_run": BUDGET_PER_RUN,
        },
    )

    t_d0 = time.time()
    results = run_discovery(output_dir, adapter, ledger, args.resume)
    t_discovery = time.time() - t_d0

    selected, sel = select_candidates(results, output_dir)
    ledger.record("candidate_selection", sel)

    t_h0 = time.time()
    holdout = run_holdout(output_dir, adapter, ledger, selected, args.resume)
    t_holdout = time.time() - t_h0

    stats = compute_statistics(results, holdout, sel)
    ledger.record("statistics_computed", {"hypotheses": stats["hypotheses"]})

    finished = _now()
    summary = {
        "protocol": protocol,
        "protocol_version": PROTOCOL_VERSION,
        "started_at": started,
        "finished_at": finished,
        "discovery_wall_time_s": t_discovery,
        "holdout_wall_time_s": t_holdout,
        "total_wall_time_s": time.time() - t0,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "config": {
            "adapter": ADAPTER_NAME,
            "adapter_version": adapter.version,
            "planner": PLANNER_NAME,
            "discovery_seeds": DISCOVERY_SEEDS,
            "selection_seed": SELECTION_SEED,
            "perturbation_pool": PERTURB_POOL,
            "perturbation_scheme": PERTURBATION_SCHEME,
            "perturbation_bands": BANDS.to_dict(),
            "holdout_reps": HOLDOUT_REPS,
            "stable_min_confirm": STABLE_MIN_CONFIRM,
            "budget_per_run": BUDGET_PER_RUN,
            "max_steps": MAX_STEPS,
            "n_test": N_TEST,
        },
        "statistics": stats,
        "selection": sel,
        "n_discovery_episodes": stats["random"]["total_launched"]
        + stats["mutation"]["total_launched"],
        "n_holdout_episodes": stats["random"]["perturbation_trials"]
        + stats["mutation"]["perturbation_trials"],
    }
    _write_json(output_dir / "summary.json", summary)
    generate_report(output_dir, summary, sel)

    ok, bad_seq = ledger.verify_chain()
    ledger.record("run_finished", {"chain_ok": ok, "first_bad_seq": bad_seq, "finished_at": finished})
    build_manifest(str(output_dir))

    h = stats["hypotheses"]
    print(f"protocol v2 complete -> {output_dir}")
    print(f"  discovery {summary['n_discovery_episodes']} episodes in {t_discovery:.1f}s")
    print(f"  holdout   {summary['n_holdout_episodes']} episodes in {t_holdout:.1f}s")
    for m in METHODS:
        s = stats[m]
        print(
            f"  {m:9s} tested={s['tested_candidates']} stable={s['stable_candidates']} "
            f"yield={s['stable_yield']:.4f} "
            f"[{s['stable_yield_wilson_95'][0]:.4f}, {s['stable_yield_wilson_95'][2]:.4f}]"
        )
    print(f"  H1 random stability supported : {h['H1_stability_random']['supported']}")
    print(f"  H2 method difference supported: {h['H2_method_difference']['supported']}")
    print(f"  H3 discovery replication      : {h['H3_discovery_yield_replication']['supported']}")
    print(f"  ledger chain ok={ok} first_bad={bad_seq}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
