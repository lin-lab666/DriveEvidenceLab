# Example case pack

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
(2101), 16-episode mutation search.  This is a demo artifact, not a formal
experiment result (see docs/LIMITATIONS.md).
