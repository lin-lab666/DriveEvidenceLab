#!/usr/bin/env python3
"""Run DriveEvidenceLab Gate E formal experiment per PROTOCOL-frozen-v1.md.

This script is intentionally self-contained and deterministic. It hardcodes the
protocol parameters so that the experiment can be reproduced from a single
source file plus the frozen protocol document.

Design notes (deviations from protocol are documented explicitly):
- Discovery seeds 2000-2063, one SearchReport per method per seed, budget=64.
- Unique candidates per method are deduplicated by scenario_hash (first seen).
- Holdout seeds 3000-3019 are reused round-robin: candidate j gets
  HOLDOUT_SEEDS[(j+offset) % 20] for offset in 0..2. This gives each unique
  candidate 3 independent holdout seeds while staying within the 20-seed pool.
- Stable failure criterion: at least 1 of 3 holdout runs reproduces the SAME
  failure category as the discovery nomination.
- Paired bootstrap is performed on per-master-seed discovery_yield differences
  (mutation - random) using B=2000, seed=2026, alpha=0.05, as required by
  the protocol. Stable yield comparison is reported separately with Wilson CI
  and Cohen's h because stable yield is aggregated across the 64 discovery runs
  and cannot be paired by master seed without deviating from the shared holdout
  seed pool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Add src to path when invoked directly.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from driveevidence.evidence import (  # noqa: E402
    EpisodeStore,
    RunLedger,
    build_manifest,
)
from driveevidence.scenario.ir import ScenarioIR  # noqa: E402
from driveevidence.search.base import Budget, FailureCandidate, SearchReport  # noqa: E402
from driveevidence.search.mutation_search import MutationSearch  # noqa: E402
from driveevidence.search.random_search import RandomSearch  # noqa: E402
from driveevidence.sim import create_adapter  # noqa: E402
from driveevidence.sim.base import EpisodeResult, FailureCategory  # noqa: E402


# ---------------------------------------------------------------------------
# Frozen protocol parameters (source: docs/PROTOCOL-frozen-v1.md)
# ---------------------------------------------------------------------------
PROTOCOL_FILE = "docs/PROTOCOL-frozen-v1.md"
METHODS = ["random", "mutation"]
DISCOVERY_SEEDS = list(range(2000, 2064))  # 64 master seeds
HOLDOUT_SEEDS = list(range(3000, 3020))    # 20 holdout seeds
BUDGET_PER_RUN = 64
MAX_STEPS = 80
ADAPTER_NAME = "builtin"
PLANNER_NAME = "safe_follow"
ROAD_LENGTH_M = 500.0
LANES = 3
LANE_WIDTH_M = 3.7
SPEED_LIMIT_MPS = 33.0
HOLDOUT_REPLICATIONS = 3
CONFIRMATION_CATEGORIES = {
    FailureCategory.COLLISION,
    FailureCategory.OFF_ROAD,
    FailureCategory.NEAR_MISS,
    FailureCategory.RULE_VIOLATION,
}
CONFIRMATION_CATEGORY_VALUES = {fc.value for fc in CONFIRMATION_CATEGORIES}

# Statistical parameters from protocol
BOOTSTRAP_B = 2000
BOOTSTRAP_SEED = 2026
BOOTSTRAP_ALPHA = 0.05

# Holdout budget cap from protocol §3: "确认阶段每候选 ≤3 holdout seeds
# （总确认 ≤ 96 seeds）". With 3 seeds per candidate this caps confirmation at
# 32 candidates total. We allocate 16 per method in first-seen order.
# Note: protocol §4 mentions "共 60 个" holdout seeds (20 unique seeds × 3
# uses), which is internally inconsistent with the §3 budget cap of 96 seeds.
# We resolve this ambiguity in favor of the explicit §3 budget cap and document
# the discrepancy. Raw holdout results for all candidates are still archived as
# evidence; the primary analysis uses only the first 16 candidates per method.
HOLDOUT_CAP_CANDIDATES_TOTAL = 32
HOLDOUT_CAP_CANDIDATES_PER_METHOD = 16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _protocol_path() -> Path:
    return _PROJECT_ROOT / PROTOCOL_FILE


def _load_protocol_hash() -> str:
    path = _protocol_path()
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
        candidates=[FailureCandidate(**c) for c in d["candidates"]],
        n_episodes=d["n_episodes"],
        episode_summaries=d["episode_summaries"],
    )


def _run_search(
    method: str,
    master_seed: int,
    adapter: Any,
    budget: Budget,
    max_steps: int,
) -> SearchReport:
    common = {
        "road_length_m": ROAD_LENGTH_M,
        "lanes": LANES,
        "lane_width_m": LANE_WIDTH_M,
        "speed_limit_mps": SPEED_LIMIT_MPS,
        "max_steps": max_steps,
    }
    if method == "random":
        searcher = RandomSearch(**common)
    else:
        searcher = MutationSearch(**common)
    return searcher.search(adapter, budget, master_seed=master_seed)


def _run_episode(
    adapter: Any,
    scenario: ScenarioIR,
    seed: int,
    max_steps: int,
) -> EpisodeResult:
    return adapter.run_episode(
        scenario,
        seed=seed,
        planner_name=PLANNER_NAME,
        config={"max_steps": max_steps},
    )


def _count_failures(summaries: List[Dict[str, Any]]) -> int:
    return sum(
        1 for s in summaries if s.get("failure_category") in CONFIRMATION_CATEGORY_VALUES
    )


# ---------------------------------------------------------------------------
# Discovery phase
# ---------------------------------------------------------------------------
def run_discovery_phase(
    output_dir: Path,
    adapter: Any,
    ledger: RunLedger,
    resume: bool = True,
) -> Dict[str, Dict[int, SearchReport]]:
    """Run all 64 discovery seeds for both methods. Resume if report exists."""
    results: Dict[str, Dict[int, SearchReport]] = {m: {} for m in METHODS}

    for method in METHODS:
        method_dir = _ensure_dir(output_dir / "discovery" / method)
        for seed in DISCOVERY_SEEDS:
            seed_dir = _ensure_dir(method_dir / f"seed_{seed}")
            report_path = seed_dir / "report.json"

            if resume and report_path.exists():
                try:
                    results[method][seed] = _report_from_dict(_read_json(report_path))
                    continue
                except Exception as exc:  # corrupted report; re-run
                    ledger.record(
                        "discovery_corrupted_report",
                        {"method": method, "master_seed": seed, "error": str(exc)},
                    )

            t0 = time.time()
            budget = Budget(max_episodes=BUDGET_PER_RUN)
            report = _run_search(method, seed, adapter, budget, MAX_STEPS)
            wall = time.time() - t0

            _write_json(report_path, _report_to_dict(report))

            ledger.record(
                "discovery_run",
                {
                    "method": method,
                    "master_seed": seed,
                    "n_episodes": report.n_episodes,
                    "n_candidates": len(report.candidates),
                    "budget_snapshot": report.budget_snapshot,
                    "wall_time_s": wall,
                    "report_path": str(report_path.relative_to(_PROJECT_ROOT)),
                },
            )
            results[method][seed] = report

    return results


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------
def collect_unique_candidates(
    results: Dict[str, Dict[int, SearchReport]],
) -> Dict[str, List[Tuple[int, FailureCandidate]]]:
    """Per method, collect unique candidates keyed by scenario_hash.

    Returns a list of (discovery_master_seed, candidate) in first-seen order.
    """
    out: Dict[str, List[Tuple[int, FailureCandidate]]] = {m: [] for m in METHODS}
    seen: Dict[str, set] = {m: set() for m in METHODS}

    for method in METHODS:
        for seed in DISCOVERY_SEEDS:
            report = results[method][seed]
            for cand in report.candidates:
                if cand.scenario_hash not in seen[method]:
                    seen[method].add(cand.scenario_hash)
                    out[method].append((seed, cand))

    return out


# ---------------------------------------------------------------------------
# Holdout phase
# ---------------------------------------------------------------------------
def run_holdout_phase(
    output_dir: Path,
    adapter: Any,
    ledger: RunLedger,
    unique_candidates: Dict[str, List[Tuple[int, FailureCandidate]]],
    resume: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """Run 3 holdout seeds per unique candidate per method."""
    holdout_results: Dict[str, List[Dict[str, Any]]] = {m: [] for m in METHODS}
    store = EpisodeStore(str(output_dir))

    for method in METHODS:
        method_h_dir = _ensure_dir(output_dir / "holdout" / method)
        for idx, (discovery_seed, cand) in enumerate(unique_candidates[method]):
            h_seeds = [
                HOLDOUT_SEEDS[(idx + offset) % len(HOLDOUT_SEEDS)]
                for offset in range(HOLDOUT_REPLICATIONS)
            ]

            cand_label = f"cand_{idx:04d}_{cand.scenario_hash[:12]}"
            cand_dir = _ensure_dir(method_h_dir / cand_label)
            scenario = ScenarioIR.from_dict(cand.scenario_dict)

            confirmations: List[Dict[str, Any]] = []
            for h_seed in h_seeds:
                result_path = cand_dir / f"seed_{h_seed}.json"
                if resume and result_path.exists():
                    result = EpisodeResult.from_dict(_read_json(result_path))
                else:
                    result = _run_episode(adapter, scenario, h_seed, MAX_STEPS)
                    _write_json(result_path, result.to_dict())

                confirmed = (
                    result.failure_category in CONFIRMATION_CATEGORIES
                    and result.failure_category.value == cand.failure_category
                )
                confirmations.append({
                    "holdout_seed": h_seed,
                    "failure_category": result.failure_category.value,
                    "confirmed": confirmed,
                    "steps": result.steps,
                    "metrics": dict(result.metrics),
                })

            confirmed_count = sum(1 for c in confirmations if c["confirmed"])
            stable = confirmed_count >= 1

            entry = {
                "method": method,
                "candidate_index": idx,
                "scenario_hash": cand.scenario_hash,
                "discovery_master_seed": discovery_seed,
                "discovery_seed": cand.discovery_seed,
                "nominated_category": cand.failure_category,
                "holdout_seeds": h_seeds,
                "confirmations": confirmations,
                "confirmed_count": confirmed_count,
                "stable": stable,
            }
            _write_json(cand_dir / "summary.json", entry)
            holdout_results[method].append(entry)

            # Archive confirmed scenario+result for replay audit.
            first_confirmed = next(
                (c for c in confirmations if c["confirmed"]), confirmations[0]
            )
            # Re-run one confirmed holdout (or first holdout) to store episode.
            # Builtin is deterministic, so this equals the stored result.
            replay_seed = first_confirmed["holdout_seed"]
            stored_result = _run_episode(adapter, scenario, replay_seed, MAX_STEPS)
            store.save(
                scenario,
                stored_result,
                extra={
                    "method": method,
                    "candidate_index": idx,
                    "discovery_master_seed": discovery_seed,
                    "holdout": True,
                    "stable": stable,
                },
            )

            ledger.record(
                "holdout_candidate",
                {
                    "method": method,
                    "candidate_index": idx,
                    "scenario_hash": cand.scenario_hash,
                    "stable": stable,
                    "confirmed_count": confirmed_count,
                    "total_replications": len(confirmations),
                },
            )

    return holdout_results


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def compute_statistics(
    results: Dict[str, Dict[int, SearchReport]],
    holdout_results: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    from driveevidence.stats.estimators import (
        cohens_h,
        paired_bootstrap_ci,
        stable_failure_yield,
        wilson_ci,
    )

    stats: Dict[str, Any] = {}

    for method in METHODS:
        launched = 0
        completed = 0
        infeasible = 0
        failed = 0
        failures = 0
        for seed in DISCOVERY_SEEDS:
            snap = results[method][seed].budget_snapshot
            launched += snap["launched"]
            completed += snap["completed"]
            infeasible += snap["infeasible"]
            failed += snap["failed"]
            failures += _count_failures(results[method][seed].episode_summaries)

        # Protocol primary analysis: cap confirmation budget at 16 candidates
        # per method (32 total), as required by protocol §3 (≤96 holdout seeds).
        # All remaining nominated candidates are counted as NOT confirmed.
        nominated = len(holdout_results[method])
        confirmed_full = sum(1 for e in holdout_results[method] if e["stable"])
        capped_entries = holdout_results[method][:HOLDOUT_CAP_CANDIDATES_PER_METHOD]
        confirmed_cap = sum(1 for e in capped_entries if e["stable"])

        point_full, (lo_full, _, hi_full) = stable_failure_yield(
            confirmed_full, nominated, z=1.96
        )
        point_cap, (lo_cap, _, hi_cap) = stable_failure_yield(
            confirmed_cap, nominated, z=1.96
        )

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
            "nominated_candidates": nominated,
            "confirmed_candidates_full": confirmed_full,
            "stable_failure_yield_full": point_full,
            "stable_failure_yield_full_wilson_95": (lo_full, point_full, hi_full),
            "confirmed_candidates_protocol_cap": confirmed_cap,
            "stable_failure_yield_protocol_cap": point_cap,
            "stable_failure_yield_protocol_cap_wilson_95": (lo_cap, point_cap, hi_cap),
        }

    # Paired bootstrap on discovery yield differences per master seed.
    random_yields: List[float] = []
    mutation_yields: List[float] = []
    for seed in DISCOVERY_SEEDS:
        r_launched = results["random"][seed].budget_snapshot["launched"]
        m_launched = results["mutation"][seed].budget_snapshot["launched"]
        r_fail = _count_failures(results["random"][seed].episode_summaries)
        m_fail = _count_failures(results["mutation"][seed].episode_summaries)
        random_yields.append(r_fail / r_launched if r_launched else 0.0)
        mutation_yields.append(m_fail / m_launched if m_launched else 0.0)

    diffs = [m - r for m, r in zip(mutation_yields, random_yields)]
    boot_lo, boot_hi = paired_bootstrap_ci(
        diffs, n_boot=BOOTSTRAP_B, seed=BOOTSTRAP_SEED, alpha=BOOTSTRAP_ALPHA
    )

    stats["comparison"] = {
        "metric": "discovery_yield_difference (mutation - random)",
        "n_pairs": len(diffs),
        "mean_diff": float(np.mean(diffs)),
        "median_diff": float(np.median(diffs)),
        "std_diff": float(np.std(diffs, ddof=1)),
        "paired_bootstrap_95_ci": (boot_lo, boot_hi),
        "bootstrap_b": BOOTSTRAP_B,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_alpha": BOOTSTRAP_ALPHA,
        "random_median_yield": float(np.median(random_yields)),
        "mutation_median_yield": float(np.median(mutation_yields)),
        "random_mean_yield": float(np.mean(random_yields)),
        "mutation_mean_yield": float(np.mean(mutation_yields)),
    }

    # Stable yield comparison (per-method aggregate; not paired by seed).
    # Primary comparison uses protocol-capped yield to respect the holdout
    # budget. A secondary full-budget Cohen's h is also reported for sensitivity.
    p_random_cap = stats["random"]["stable_failure_yield_protocol_cap"]
    p_mutation_cap = stats["mutation"]["stable_failure_yield_protocol_cap"]
    stats["comparison"]["stable_yield_cohens_h_protocol_cap"] = cohens_h(
        p_mutation_cap, p_random_cap
    )
    p_random_full = stats["random"]["stable_failure_yield_full"]
    p_mutation_full = stats["mutation"]["stable_failure_yield_full"]
    stats["comparison"]["stable_yield_cohens_h_full"] = cohens_h(
        p_mutation_full, p_random_full
    )
    stats["comparison"]["holdout_cap_total_candidates"] = HOLDOUT_CAP_CANDIDATES_TOTAL
    stats["comparison"]["holdout_cap_per_method"] = HOLDOUT_CAP_CANDIDATES_PER_METHOD

    return stats


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_markdown_report(output_dir: Path, summary: Dict[str, Any]) -> Path:
    stats = summary["statistics"]
    lines = [
        "# DriveEvidenceLab｜Gate E 正式实验报告",
        "",
        f"- 协议文件：`{PROTOCOL_FILE}`",
        f"- 协议 SHA-256（按当前文件内容实际计算）：`{summary.get('protocol_sha256', 'N/A')}`",
        f"- 协议文件末尾声明的 SHA-256：`247f6721ee26ae76e7e9258e3e43065ea2189fe4d37254ff62b8074ae8e92e29`",
        "- ⚠️ 注意：文件末尾声明的 hash 与文件实际内容 hash 不一致；实验以实际内容 hash 为准，并记录此协议自签异常。",
        f"- 实验完成时间：{summary.get('finished_at', 'N/A')}",
        f"- 发现阶段 wall time：{summary['discovery_wall_time_s']:.1f}s",
        f"- Holdout 阶段 wall time：{summary['holdout_wall_time_s']:.1f}s",
        "",
        "## 执行配置",
        "",
        f"- 仿真后端：{ADAPTER_NAME}",
        f"- 规划器：{PLANNER_NAME}",
        f"- 每方法发现阶段：{len(DISCOVERY_SEEDS)} 个 master seed × {BUDGET_PER_RUN} episodes",
        f"- Holdout 池：{len(HOLDOUT_SEEDS)} 个独立 seed，每个候选复测 {HOLDOUT_REPLICATIONS} 次",
        f"- 稳定失败判据：3 次 holdout 中至少 1 次复现同类型 failure",
        "",
        "## 结果摘要（协议 primary：holdout 确认预算 capped）",
        "",
        "| 方法 | 总发起 episodes | discovery failures | discovery yield | 提名数 | capped 确认数 | stable yield (cap) | Wilson 95% CI |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for method in METHODS:
        s = stats[method]
        lo, hi = s["discovery_yield_wilson_95"]
        s_lo, _, s_hi = s["stable_failure_yield_protocol_cap_wilson_95"]
        lines.append(
            f"| {method} | {s['total_launched']} | {s['discovery_failures']} | "
            f"{s['discovery_yield']:.4f} [{lo:.4f}, {hi:.4f}] | "
            f"{s['nominated_candidates']} | {s['confirmed_candidates_protocol_cap']} | "
            f"{s['stable_failure_yield_protocol_cap']:.4f} [{s_lo:.4f}, {s_hi:.4f}] |"
        )
    lines.extend([
        "",
        "## 算法比较",
        "",
        f"- 指标：{stats['comparison']['metric']}",
        f"- 配对数：{stats['comparison']['n_pairs']}",
        f"- 平均差值：{stats['comparison']['mean_diff']:.4f}",
        f"- 中位差值：{stats['comparison']['median_diff']:.4f}",
        f"- 标准差：{stats['comparison']['std_diff']:.4f}",
        f"- 配对 bootstrap 95% CI：[{stats['comparison']['paired_bootstrap_95_ci'][0]:.4f}, {stats['comparison']['paired_bootstrap_95_ci'][1]:.4f}]",
        f"- Cohen's h (stable yield, protocol cap)：{stats['comparison']['stable_yield_cohens_h_protocol_cap']:.4f}",
        "",
        "## 协议解释与已知偏差",
        "",
        f"1. 配对 bootstrap 严格按协议在 64 个 master seed 的 discovery_yield 差值上进行（B={BOOTSTRAP_B}，seed={BOOTSTRAP_SEED}）。",
        f"2. Holdout 确认预算：协议 §3 规定'总确认 ≤ {HOLDOUT_CAP_CANDIDATES_TOTAL * HOLDOUT_REPLICATIONS} seeds'，即最多确认 {HOLDOUT_CAP_CANDIDATES_TOTAL} 个候选（每方法 {HOLDOUT_CAP_CANDIDATES_PER_METHOD} 个）。",
        "   所有被提名但未在预算内确认的候选，按稳定失败判据计为未确认（stable=False）。",
        "3. 实际搜索发现了远多于 32 个的独特候选；全部 holdout 已运行并归档，但 primary stable yield 仅使用 capped 子集。",
        "4. 协议 §4 提到'共 60 个' holdout seeds，与 §3 的 96-seed 总预算存在内部不一致。本实验采用 §3 的显式预算上限并记录此差异。",
        "5. Holdout seed 分配：候选 j 依次获得 3000+(j mod 20)、3000+((j+1) mod 20)、3000+((j+2) mod 20) 三个独立 seed。",
        "",
        "## 敏感性分析（无限确认预算假设）",
        "",
        "以下结果基于全部候选的 holdout 确认，仅供稳健性参考，不是协议 primary 指标：",
        "",
        "| 方法 | 提名数 | 确认数 | stable yield (full) | Wilson 95% CI |",
        "|---|---|---|---|---|",
    ])
    for method in METHODS:
        s = stats[method]
        s_lo, _, s_hi = s["stable_failure_yield_full_wilson_95"]
        lines.append(
            f"| {method} | {s['nominated_candidates']} | {s['confirmed_candidates_full']} | "
            f"{s['stable_failure_yield_full']:.4f} [{s_lo:.4f}, {s_hi:.4f}] |"
        )
    lines.extend([
        "",
        "## 研究结论边界",
        "",
        "- 结论仅限 builtin 仿真器 + safe_follow 规划器在 straight-road 3 车道场景族内的表现。",
        "- 任何真实道路安全外推均被禁止。",
        "- H1（stable failure yield > 0）的判定以 protocol-capped Wilson 95% 下界为准；H2（方法差异）的判定以配对 bootstrap CI 是否包含 0 为准。",
    ])

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Gate E formal experiment")
    parser.add_argument(
        "--out",
        default="runs/formal_experiment_v1",
        help="Output directory for the formal experiment",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Skip already completed discovery/holdout runs",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Force re-run everything",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Skip execution; only analyze existing results in --out",
    )
    args = parser.parse_args(argv)

    resume = not args.no_resume and args.resume
    output_dir = Path(args.out).resolve()
    _ensure_dir(output_dir)

    protocol_hash = _load_protocol_hash()
    protocol_snapshot = {
        "protocol_file": PROTOCOL_FILE,
        "protocol_sha256": protocol_hash,
        "methods": METHODS,
        "discovery_seeds": DISCOVERY_SEEDS,
        "holdout_seeds": HOLDOUT_SEEDS,
        "budget_per_run": BUDGET_PER_RUN,
        "max_steps": MAX_STEPS,
        "adapter": ADAPTER_NAME,
        "planner": PLANNER_NAME,
        "holdout_replications": HOLDOUT_REPLICATIONS,
        "started_at": _now(),
    }
    _write_json(output_dir / "protocol_snapshot.json", protocol_snapshot)

    ledger = RunLedger(
        str(output_dir), "formal_experiment_v1", config=protocol_snapshot
    )

    adapter = create_adapter(ADAPTER_NAME)

    if args.audit_only:
        # Load existing results and compute statistics.
        results = {m: {} for m in METHODS}
        for method in METHODS:
            method_dir = output_dir / "discovery" / method
            for seed in DISCOVERY_SEEDS:
                report_path = method_dir / f"seed_{seed}" / "report.json"
                if not report_path.exists():
                    print(f"Missing discovery report: {report_path}", file=sys.stderr)
                    return 1
                results[method][seed] = _report_from_dict(_read_json(report_path))
        unique_candidates = collect_unique_candidates(results)
        holdout_results = {m: [] for m in METHODS}
        for method in METHODS:
            method_h_dir = output_dir / "holdout" / method
            for idx, (discovery_seed, cand) in enumerate(unique_candidates[method]):
                cand_label = f"cand_{idx:04d}_{cand.scenario_hash[:12]}"
                summary_path = method_h_dir / cand_label / "summary.json"
                if not summary_path.exists():
                    print(f"Missing holdout summary: {summary_path}", file=sys.stderr)
                    return 1
                holdout_results[method].append(_read_json(summary_path))
        stats = compute_statistics(results, holdout_results)
        summary = {
            "protocol_sha256": protocol_hash,
            "audit_only": True,
            "per_method": {
                m: {
                    "n_runs": len(results[m]),
                    "n_unique_candidates": len(unique_candidates[m]),
                }
                for m in METHODS
            },
            "statistics": stats,
            "finished_at": _now(),
        }
        _write_json(output_dir / "summary.json", summary)
        report_path = generate_markdown_report(output_dir, summary)
        print(f"Audit-only report: {report_path}")
        return 0

    t_discovery_0 = time.time()
    results = run_discovery_phase(output_dir, adapter, ledger, resume=resume)
    t_discovery = time.time() - t_discovery_0

    unique_candidates = collect_unique_candidates(results)

    t_holdout_0 = time.time()
    holdout_results = run_holdout_phase(
        output_dir, adapter, ledger, unique_candidates, resume=resume
    )
    t_holdout = time.time() - t_holdout_0

    stats = compute_statistics(results, holdout_results)

    summary = {
        "protocol_sha256": protocol_hash,
        "discovery_wall_time_s": t_discovery,
        "holdout_wall_time_s": t_holdout,
        "total_wall_time_s": t_discovery + t_holdout,
        "per_method": {
            m: {
                "n_runs": len(results[m]),
                "n_unique_candidates": len(unique_candidates[m]),
            }
            for m in METHODS
        },
        "statistics": stats,
        "finished_at": _now(),
    }
    _write_json(output_dir / "summary.json", summary)
    report_path = generate_markdown_report(output_dir, summary)

    n_discovery_episodes = sum(
        results[m][s].n_episodes for m in METHODS for s in DISCOVERY_SEEDS
    )
    n_holdout_episodes = sum(
        len(e["confirmations"]) for m in METHODS for e in holdout_results[m]
    )
    ledger.record(
        RunLedger.EVENT_RUN_FINISHED,
        {
            "total_wall_time_s": t_discovery + t_holdout,
            "n_discovery_episodes": n_discovery_episodes,
            "n_holdout_episodes": n_holdout_episodes,
            "report_path": str(report_path.relative_to(_PROJECT_ROOT)),
        },
    )

    build_manifest(str(output_dir))
    print(f"Formal experiment complete: {output_dir}")
    print(f"Discovery time: {t_discovery:.1f}s, Holdout time: {t_holdout:.1f}s")
    print(
        f"Random stable yield (protocol cap): {stats['random']['stable_failure_yield_protocol_cap']:.3f} "
        f"[{stats['random']['stable_failure_yield_protocol_cap_wilson_95'][0]:.3f}, "
        f"{stats['random']['stable_failure_yield_protocol_cap_wilson_95'][2]:.3f}]"
    )
    print(
        f"Mutation stable yield (protocol cap): {stats['mutation']['stable_failure_yield_protocol_cap']:.3f} "
        f"[{stats['mutation']['stable_failure_yield_protocol_cap_wilson_95'][0]:.3f}, "
        f"{stats['mutation']['stable_failure_yield_protocol_cap_wilson_95'][2]:.3f}]"
    )
    print(
        f"Discovery yield mean diff (mutation - random): "
        f"{stats['comparison']['mean_diff']:.4f}"
    )
    print(
        f"Bootstrap 95% CI: ["
        f"{stats['comparison']['paired_bootstrap_95_ci'][0]:.4f}, "
        f"{stats['comparison']['paired_bootstrap_95_ci'][1]:.4f}]"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
