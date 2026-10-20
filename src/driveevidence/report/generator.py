"""Generate human-readable experiment reports from a run directory."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from driveevidence.evidence import verify_manifest
from driveevidence.evidence.episode_store import EpisodeStore
from driveevidence.evidence.ledger import RunLedger


@dataclass
class ReportSummary:
    run_id: str
    adapter: str
    method: str
    n_episodes: int
    failure_counts: Dict[str, int]
    budget: Dict[str, int]
    manifest_ok: bool
    ledger_ok: bool
    candidates: List[Dict[str, Any]]


def load_report(run_dir: str) -> ReportSummary:
    run_path = Path(run_dir)
    ledger = RunLedger.load(run_dir)
    ledger_ok, _ = ledger.verify_chain()
    manifest_results = verify_manifest(run_dir)
    manifest_ok = manifest_results.get("__manifest__") == "ok" and all(
        v == "ok" for k, v in manifest_results.items() if k != "__manifest__"
    )

    first = ledger.entries()[0]
    config = first["payload"].get("config", {})

    failure_counts: Dict[str, int] = {}
    candidates: List[Dict[str, Any]] = []
    budget: Dict[str, int] = {}
    n_episodes = 0

    store = EpisodeStore(run_dir)
    for seq, scenario, result, extra in store.iter_all():
        n_episodes += 1
        cat = result.failure_category.value
        failure_counts[cat] = failure_counts.get(cat, 0) + 1
        if cat in {"collision", "off_road", "near_miss", "rule_violation"}:
            candidates.append({
                "seq": seq,
                "scenario_id": result.scenario_id,
                "scenario_hash": result.scenario_hash,
                "failure_category": cat,
                "failure_detail": result.failure_detail,
                "metrics": result.metrics,
            })

    # Try to recover budget from ledger budget_snapshot entries.
    for entry in ledger.entries():
        if entry["type"] == RunLedger.EVENT_BUDGET_SNAPSHOT:
            budget = entry["payload"].get("snapshot", {})
            break
    if not budget and config:
        budget = config.get("budget", {})

    return ReportSummary(
        run_id=ledger.run_id,
        adapter=config.get("adapter", "unknown"),
        method=config.get("method", "unknown"),
        n_episodes=n_episodes,
        failure_counts=failure_counts,
        budget=budget,
        manifest_ok=manifest_ok,
        ledger_ok=ledger_ok,
        candidates=candidates,
    )


def generate_markdown(run_dir: str, out_path: Optional[str] = None) -> str:
    summary = load_report(run_dir)
    lines = [
        f"# DriveEvidenceLab Run Report: {summary.run_id}",
        "",
        f"- **Adapter**: {summary.adapter}",
        f"- **Method**: {summary.method}",
        f"- **Episodes**: {summary.n_episodes}",
        f"- **Ledger integrity**: {'PASS' if summary.ledger_ok else 'FAIL'}",
        f"- **Manifest integrity**: {'PASS' if summary.manifest_ok else 'FAIL'}",
        "",
        "## Failure distribution",
        "",
    ]
    for cat, count in sorted(summary.failure_counts.items()):
        lines.append(f"- `{cat}`: {count}")
    lines.append("")
    lines.append("## Budget snapshot")
    lines.append("")
    for key, value in sorted(summary.budget.items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Failure candidates")
    lines.append("")
    for cand in summary.candidates[:20]:
        lines.append(
            f"- seq={cand['seq']} `{cand['scenario_id']}` "
            f"({cand['failure_category']}): {cand['failure_detail']}"
        )
    if len(summary.candidates) > 20:
        lines.append(f"- ... and {len(summary.candidates) - 20} more")
    lines.append("")
    lines.append(
        "_This report is generated from raw evidence files in the run directory. "
        "It makes no real-world safety claims._"
    )
    text = "\n".join(lines)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    return text


def generate_html(run_dir: str, out_path: Optional[str] = None) -> str:
    summary = load_report(run_dir)
    rows = "".join(
        f"<tr><td>{cat}</td><td>{count}</td></tr>"
        for cat, count in sorted(summary.failure_counts.items())
    )
    budget_rows = "".join(
        f"<tr><td>{key}</td><td>{value}</td></tr>"
        for key, value in sorted(summary.budget.items())
    )
    cand_rows = "".join(
        f"<tr><td>{c['seq']}</td><td>{c['scenario_id']}</td>"
        f"<td>{c['failure_category']}</td></tr>"
        for c in summary.candidates[:20]
    )
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Run Report {summary.run_id}</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; margin: 1em 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.4em; }}
th {{ background: #eee; }}
</style>
</head>
<body>
<h1>DriveEvidenceLab Run Report: {summary.run_id}</h1>
<ul>
<li>Adapter: <code>{summary.adapter}</code></li>
<li>Method: <code>{summary.method}</code></li>
<li>Episodes: {summary.n_episodes}</li>
<li>Ledger integrity: {'PASS' if summary.ledger_ok else 'FAIL'}</li>
<li>Manifest integrity: {'PASS' if summary.manifest_ok else 'FAIL'}</li>
</ul>
<h2>Failure distribution</h2>
<table><tr><th>Category</th><th>Count</th></tr>{rows}</table>
<h2>Budget snapshot</h2>
<table><tr><th>Key</th><th>Value</th></tr>{budget_rows}</table>
<h2>Failure candidates</h2>
<table><tr><th>Seq</th><th>Scenario</th><th>Category</th></tr>{cand_rows}</table>
<p><em>This report is generated from raw evidence files. It makes no real-world safety claims.</em></p>
</body>
</html>"""
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
    return html
