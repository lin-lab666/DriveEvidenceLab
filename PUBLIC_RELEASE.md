# Public release provenance

This directory is a **privacy-scrubbed public copy** of a private research
repository. It is not the original development history.

## What this copy is
- Built from `git ls-files` of the private repository at commit `c8f12defad812f01d71b5b8a2ee2cbda55e85c48`.
- Contains **one curated commit**. The private repository keeps the full
  incremental history; that history is not published because it contains
  local absolute paths.
- 148 files were copied. Every file's SHA-256 is recorded in
  `PUBLIC_MANIFEST.json`.

## What was removed or changed

No file required redaction.

`runs/` (raw per-episode artifacts, ~71 MB) and `.workbuddy/` (local agent
state) are not published. The raw formal-experiment artifacts are instead
distributed as the archived bundles under `evidence/`, which are the exact
inputs the audit scripts verify.

## Outstanding blockers before publication

None detected at build time.

## Freeze fingerprints that survive the scrubbing

These values let a third party verify the protocol and the evidence archive
without access to the private git history:

```json
{
  "evidence_sha256sums_lines": 2,
  "evidence_sha256sums_sha256": "8832e9de4aeef174b6bbfbbd0e442484b96ae7dfe842c693243d147b56b7aa9e",
  "protocol_v2_freeze": {
    "frozen_at_utc": "2026-10-19",
    "full_file_sha256": "0a0ac56daad4257c2a7542bcf7a4d50afe0317513a54a9fa7616eceb9054cde1",
    "git_commit": "see git log: first commit containing docs/PROTOCOL-frozen-v2.md (commit hash intentionally not embedded to avoid hash churn)",
    "hash_convention": "sha256(LF-normalised bytes before <!-- SIGNATURE -->)",
    "protocol_body_sha256": "205ecf9ff156d003887502f438dc4975bcd3a9b3e85b4a2c70feb54eea8a5137",
    "protocol_file": "docs/PROTOCOL-frozen-v2.md",
    "protocol_version": "v2.0",
    "supersedes": "docs/PROTOCOL-frozen-v1.md (stability claims invalidated)"
  }
}
```

### Verification

```bash
python scripts/verify_evidence_bundle.py        # checksums -> hash chain -> manifest -> recompute
python scripts/audit_independent_recompute.py   # statistics from scratch, no project imports
```

The independent recompute script needs the extracted run directory; see
`evidence/README.md` for how the bundles map onto `runs/` paths.

## What this copy does NOT establish

- It does not establish external (third-party) reproduction. All experiments
  were produced by one author on one machine, so conclusion layer **T3**
  remains unmet.
- It does not establish cross-simulator dynamics validation. Gate D is
  **PARTIAL**: CommonRoad scenario exchange was verified with the real
  `commonroad-io` library, but no third-party dynamics engine was integrated.
- Results are specific to the `builtin` kinematic simulator, the `safe_follow`
  planner and a single-lead-vehicle straight-road scenario family.
