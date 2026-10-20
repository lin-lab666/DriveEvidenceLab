"""Demo 3 — Replay and evidence verification with the Python SDK.

This demo is **self-contained**: it first archives a real, small falsification
search as tamper-evident evidence (hash-chained ledger + per-episode files +
manifest — exactly what the CLI's ``search`` command produces), then

  1. audits the run (ledger hash chain + manifest integrity),
  2. replays an archived episode exactly (same scenario, seed, planner,
     config) and compares the outcome,
  3. shows what a single archived evidence file contains.

No private files or absolute paths are needed — everything is created inside
a temporary directory from public API calls only.

Run from anywhere once the package is installed:

    python examples/replay_evidence_demo.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from driveevidence.evidence import EpisodeStore, RunLedger
from driveevidence.evidence.manifest import build_manifest, verify_manifest
from driveevidence.evidence.replay import replay_episode
from driveevidence.search import Budget, MutationSearch
from driveevidence.sim import create_adapter

DEMO_SEED = 2101   # same fixed teaching seed as the discovery demo
DEMO_BUDGET = 32
MAX_STEPS = 80


def main() -> int:
    print("=" * 64)
    print("DriveEvidenceLab — replay & evidence demo")
    print("=" * 64)
    adapter = create_adapter("builtin")

    # ------------------------------------------------------------------
    # 1. Run a real search and archive its failures as evidence.
    #    This mirrors what `driveevidence search` does internally.
    # ------------------------------------------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="driveevidence_demo_"))
    run_dir = tmp / "demo_search"
    run_dir.mkdir(parents=True)
    print(f"\n[1] running a small search; evidence goes to {run_dir}")

    config: Dict[str, Any] = {
        "adapter": "builtin", "method": "mutation",
        "budget": DEMO_BUDGET, "command": "demo_search",
    }
    ledger = RunLedger(str(run_dir), "demo_search", config=config)
    budget = Budget(max_episodes=DEMO_BUDGET)
    search = MutationSearch(road_length_m=500, lanes=3, max_steps=MAX_STEPS)
    report = search.search(adapter, budget, master_seed=DEMO_SEED)
    ledger.record(
        RunLedger.EVENT_BUDGET_SNAPSHOT,
        {"snapshot": report.budget_snapshot, "n_candidates": len(report.candidates)},
    )

    store = EpisodeStore(str(run_dir))
    for candidate in report.candidates:
        scenario = ScenarioIR_from(candidate)
        result = adapter.run_episode(
            scenario, seed=candidate.discovery_seed, planner_name="safe_follow",
            config={"max_steps": MAX_STEPS},
        )
        store.save(scenario, result, extra={"candidate": True, "method": "mutation"})
    ledger.record(RunLedger.EVENT_RUN_FINISHED, {"n_episodes": report.n_episodes})
    build_manifest(str(run_dir))

    n_archived = len(list((run_dir / "episodes").glob("*.json")))
    print(f"    {len(report.candidates)} candidate(s); {n_archived} episode file(s) archived")

    # ------------------------------------------------------------------
    # 2. Audit: verify the ledger hash chain and the manifest hashes.
    # ------------------------------------------------------------------
    print("\n[2] auditing evidence ...")
    loaded = RunLedger.load(str(run_dir))
    chain_ok, bad_seq = loaded.verify_chain()
    print(f"    ledger hash chain : {'PASS' if chain_ok else 'FAIL (first bad seq: ' + str(bad_seq) + ')'}")
    manifest = verify_manifest(str(run_dir))
    manifest_ok = manifest.get("__manifest__") == "ok" and all(
        v == "ok" for k, v in manifest.items() if k != "__manifest__"
    )
    print(f"    manifest integrity: {'PASS' if manifest_ok else 'FAIL'}")
    if not (chain_ok and manifest_ok):
        return 1

    # ------------------------------------------------------------------
    # 3. Replay: re-run an archived episode exactly and compare.
    # ------------------------------------------------------------------
    available = sorted(int(p.stem) for p in (run_dir / "episodes").glob("*.json"))
    if not available:
        print("    no episodes archived — nothing to replay")
        return 1
    seq = available[0]
    scenario, original, extra = store.load(seq)
    print(f"\n[3] replaying archived episode {seq:04d} "
          f"(scenario {scenario.scenario_id}, seed {original.seed}) ...")
    outcome = replay_episode(str(run_dir), seq, adapter)
    print(f"    original category : {outcome.original_category}")
    print(f"    replayed category : {outcome.replayed_category}")
    print(f"    category match    : {outcome.category_match}")
    diffs = {k: round(v, 12) for k, v in outcome.metric_diffs.items()}
    print(f"    metric diffs      : {diffs}")
    exact = all(v == 0.0 for v in outcome.metric_diffs.values())
    print(f"    bit-exact replay  : {exact}")

    # ------------------------------------------------------------------
    # 4. Show what one archived evidence file contains.
    # ------------------------------------------------------------------
    print(f"\n[4] inside the archived evidence file episodes/{seq:04d}.json")
    raw = json.loads((run_dir / "episodes" / f"{seq:04d}.json").read_text(encoding="utf-8"))
    print(f"    top-level keys : {sorted(raw.keys())}")
    print(f"    result keys    : {sorted(raw['result'].keys())[:8]} ...")
    print(f"    trajectory pts : {len(raw['result'].get('trajectory') or [])}")
    print(f"    scenario ir    : {raw['scenario']['ir_version']}")

    print(
        "\nSummary: every archived failure can be re-run bit-for-bit later, and "
        "any tampering with the evidence files breaks the manifest verification."
    )
    return 0


def ScenarioIR_from(candidate):
    """Rebuild the archived scenario from a candidate record."""
    from driveevidence.scenario import ScenarioIR
    return ScenarioIR.from_dict(candidate.scenario_dict)


if __name__ == "__main__":
    sys.exit(main())
