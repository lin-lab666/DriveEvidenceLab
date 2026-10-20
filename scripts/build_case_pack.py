#!/usr/bin/env python3
"""Build the public example case pack: a small, self-contained evidence run.

The case pack ships in the repository under ``examples/case_pack/`` and lets a
stranger on a fresh machine do three things without any private files:

  1. ``driveevidence audit  --run examples/case_pack/run``   verify the ledger
     hash chain and the manifest of a pre-built run;
  2. ``driveevidence replay --run examples/case_pack/run --seq 1`` replay an
     archived failure bit-for-bit;
  3. re-generate the whole pack from scratch with this script and confirm the
     scenario hashes match (the simulator is deterministic; wall-clock fields
     will differ, which is expected and stated in the README).

The pack is produced with a fixed teaching seed (2101) and a 16-episode
mutation search, so it always contains the same failures.  It is a *demo*
artifact, not a formal experiment result.

Usage:
    python scripts/build_case_pack.py [--out examples/case_pack] [--check]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from driveevidence.evidence import EpisodeStore, RunLedger  # noqa: E402
from driveevidence.evidence.manifest import build_manifest, verify_manifest  # noqa: E402
from driveevidence.evidence.replay import replay_episode  # noqa: E402
from driveevidence.scenario import ScenarioIR  # noqa: E402
from driveevidence.search import Budget, MutationSearch  # noqa: E402
from driveevidence.sim import create_adapter  # noqa: E402

SEED = 2101
BUDGET = 16
MAX_STEPS = 80
README_TEXT = """# Example case pack

A small, self-contained evidence run produced by DriveEvidenceLab's builtin
simulator (backend `builtin/1.1`, `safe_follow` planner, deterministic).

Contents:

- `run/` — a complete evidence run: `ledger.jsonl` (hash-chained),
  `episodes/*.json` (archived failures with full trajectories),
  `manifest.json` (SHA-256 of every file).

Verify it on a fresh machine (no private files needed):

    driveevidence audit  --run examples/case_pack/run
    driveevidence replay --run examples/case_pack/run --seq 1 --adapter builtin

Re-generate it from scratch and compare scenario hashes:

    python scripts/build_case_pack.py --check

Provenance: built by `scripts/build_case_pack.py` from a fixed teaching seed
({seed}), 16-episode mutation search.  This is a demo artifact, not a formal
experiment result (see docs/LIMITATIONS.md).
""".format(seed=SEED)


def build(out_dir: Path) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="casepack_build_"))
    run_dir = tmp / "run"
    run_dir.mkdir(parents=True)

    adapter = create_adapter("builtin")
    config: Dict[str, Any] = {
        "adapter": "builtin", "method": "mutation",
        "budget": BUDGET, "command": "case_pack", "max_steps": MAX_STEPS,
    }
    ledger = RunLedger(str(run_dir), "case_pack", config=config)
    search = MutationSearch(road_length_m=500, lanes=3, max_steps=MAX_STEPS)
    report = search.search(adapter, Budget(max_episodes=BUDGET), master_seed=SEED)
    ledger.record(RunLedger.EVENT_BUDGET_SNAPSHOT,
                  {"snapshot": report.budget_snapshot,
                   "n_candidates": len(report.candidates)})
    store = EpisodeStore(str(run_dir))
    for candidate in report.candidates:
        scenario = ScenarioIR.from_dict(candidate.scenario_dict)
        result = adapter.run_episode(
            scenario, seed=candidate.discovery_seed,
            planner_name="safe_follow", config={"max_steps": MAX_STEPS},
        )
        store.save(scenario, result, extra={"candidate": True, "method": "mutation"})
    ledger.record(RunLedger.EVENT_RUN_FINISHED, {"n_episodes": report.n_episodes})
    build_manifest(str(run_dir))

    # sanity: audit + replay must pass before we ship the pack
    loaded = RunLedger.load(str(run_dir))
    chain_ok, _ = loaded.verify_chain()
    manifest = verify_manifest(str(run_dir))
    manifest_ok = manifest.get("__manifest__") == "ok" and all(
        v == "ok" for k, v in manifest.items() if k != "__manifest__"
    )
    if not (chain_ok and manifest_ok):
        raise SystemExit("built pack failed its own audit — refusing to ship")

    seqs = sorted(int(p.stem) for p in (run_dir / "episodes").glob("*.json"))
    outcome = replay_episode(str(run_dir), seqs[0], adapter)
    if not outcome.category_match:
        raise SystemExit("built pack failed replay check — refusing to ship")

    # collect the facts the --check mode compares later
    hashes = {}
    for seq in seqs:
        sc, res, _extra = store.load(seq)
        hashes[str(seq)] = res.scenario_hash

    return {
        "run_dir": run_dir,
        "staging": tmp,
        "n_candidates": len(report.candidates),
        "n_episodes": report.n_episodes,
        "episode_hashes": hashes,
        "replay_seq": seqs[0],
        "replay_exact": all(v == 0.0 for v in outcome.metric_diffs.values()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO_ROOT / "examples" / "case_pack"))
    ap.add_argument("--check", action="store_true",
                    help="rebuild in a temp dir and compare episode scenario hashes")
    args = ap.parse_args(argv)

    out = Path(args.out)
    built = build(out)

    if args.check:
        ref = out / "run"
        if not ref.exists():
            print(f"[check] no shipped pack at {ref}")
            return 1
        ref_store = EpisodeStore(str(ref))
        mismatch = 0
        for seq_str, h in built["episode_hashes"].items():
            try:
                _sc, res, _ex = ref_store.load(int(seq_str))
                if res.scenario_hash != h:
                    mismatch += 1
            except FileNotFoundError:
                mismatch += 1
        total = len(built["episode_hashes"])
        print(f"[check] rebuilt {total} episodes; scenario-hash mismatches vs shipped pack: {mismatch}")
        print(f"[check] {'MATCH' if mismatch == 0 else 'MISMATCH'}")
        return 0 if mismatch == 0 else 1

    # ship: copy run/ + README into the target.
    # All text files are normalised to LF *before* hashing: the repository's
    # .gitattributes checks text files out with LF, so the SHA256SUMS must be
    # computed over the bytes a fresh clone will actually see.
    TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".toml", ".cfg"}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(built["run_dir"], out / "run")
    for p in (out / "run").rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            data = p.read_bytes().replace(b"\r\n", b"\n")
            p.write_bytes(data)
    # The manifest recorded hashes of the pre-normalisation bytes, so rebuild
    # it over the LF bytes that a fresh clone will see.
    build_manifest(str(out / "run"))
    (out / "README.md").write_text(README_TEXT, encoding="utf-8", newline="\n")

    # SHA256SUMS over the shipped files
    import hashlib
    lines = []
    for p in sorted((out / "run").rglob("*")):
        if p.is_file():
            rel = p.relative_to(out)
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel.as_posix()}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"case pack written to {out}")
    print(f"  candidates : {built['n_candidates']}")
    print(f"  episodes   : {built['n_episodes']}")
    print(f"  replay seq {built['replay_seq']}: bit-exact={built['replay_exact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
