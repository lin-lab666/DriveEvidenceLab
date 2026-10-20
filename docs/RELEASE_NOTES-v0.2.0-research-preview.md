# DriveEvidenceLab v0.2.0 — Research Preview

> **This is a research preview, not a stable release.**
> It reports a negative result, a retracted result, and an unreplicated result.
> Read "What this release does not claim" before citing anything.

---

## What this is

A simulation-only research toolkit for **evidence-driven falsification of
autonomous-driving planners**. It couples four things that are usually separate:

1. a canonical scenario IR with deterministic cross-process hashing;
2. a search layer (random vs mutation) under a shared episode budget that is
   accounted for on every launch, failure, cancellation and infeasible case;
3. a stability measurement that perturbs *initial conditions* rather than
   re-running a deterministic function;
4. an append-only, hash-chained evidence ledger with replay and manifest
   verification.

The interesting part is not that a search algorithm found failures. It is that
the project found **two real measurement defects in its own experiment** and built
the machinery to prove they were fixed.

---

## Headline result (v2.1, `builtin/1.1`)

8192 discovery episodes + 384 holdout episodes, protocol frozen before the run.

| Method | Discovery yield [95% CI] | Nominated | Tested | Stable | Stable yield [95% CI] |
|---|---|---|---|---|---|
| random | 0.0444 [0.0385, 0.0512] | 182 | 64 | **57** | **0.890625 (57/64)** [0.7910, 0.9460] |
| mutation | 0.4114 [0.3964, 0.4265] | 1685 | 64 | **61** | **0.953125 (61/64)** [0.8710, 0.9839] |

| Hypothesis | Decision rule (pre-registered) | Result |
|---|---|---|
| H1 — random stability | Wilson 95% lower bound > 0.1 | **supported** (0.7910) |
| H2 — method difference | Newcombe 95% CI of Δ excludes 0 | **not supported** (Δ=+0.0625, CI [−0.0365, +0.1668], Fisher p=0.324) |
| H3 — discovery replication | paired bootstrap 95% CI excludes 0 | **supported** (Δ=+0.3669, CI [0.3218, 0.4124]) |

**H2 is "no detectable difference", not "the methods are equivalent."** With 64
candidates per method the design is underpowered for a six-point difference.

---

## What was retracted, and why

The first version of this experiment (v1) reported a stable yield of 100% and a
large method difference. Both were **measurement artifacts**, not results:

- The kinematic simulator constructed `rng = default_rng(seed)` and **never used
  it**. Six different seeds produced the byte-identical trajectory hash
  `1ab76b8b90eda348`; all 1716/1716 candidates were bit-identical across three
  "independent" holdout seeds.
- The primary metric was `first-16-confirmations / all-nominated`, which collapses
  to `16 / nominations` whenever everything is stable — it measured nomination
  volume, not stability.

v1's stability numbers and its H1/H2 conclusions are **withdrawn**. Its
`discovery_yield` remains valid because it does not depend on seed semantics.
The v1 artifacts are kept unmodified under `runs/formal_experiment_v1/`.

A second protocol deviation (v2.0) is also disclosed: `builtin/1.0` had a
`for ... else` bug that made the `NEAR_MISS` branch unreachable (0 near-miss in
16384 episodes). After the fix (`builtin/1.1`, run v2.1) near-miss appears 57
times and random stability moves 0.9375 (60/64) → 0.890625 (57/64).
**Both runs are kept side by side; neither was selected for looking better.**

---

## What this release does not claim

- **Not** a real-world road-safety result. Simulation only.
- **Not** externally replicated. All artifacts come from one author, one code
  base, one machine. Conclusion layer **T3 is unmet**.
- **Not** a cross-simulator validation. Gate D is **PARTIAL**: the CommonRoad
  adapter was verified against the real `commonroad-io 2026.1` library (80 real
  candidates, 0 exchange failures, identical trajectories, 80/80 identical
  failure categories) — but it reuses this project's kinematics and only swaps
  the *judging* layer. `capabilities()` reports
  `independent_dynamics=False`, `third_party_dynamics_engine=False`.
- **Not** CARLA-validated. CARLA is `NOT IMPLEMENTED`.
- **Not** general across scenario families. One lead vehicle, straight 3-lane
  road, one rule-based planner. In this family `off_road` and `rule_violation`
  are structurally near-unreachable, so the four failure classes collapse to
  collision / near-miss / timeout.
- **Not** proof that the methods are equivalent (see H2 above).

The full itemised disclosure is in `docs/LIMITATIONS.md`.

---

## Reproducing

```bash
pip install -e ".[sim,dev]"
python -m unittest discover -s tests -p "test_*.py"    # 156 tests
bash scripts/run_all.sh                                # audit + evidence bundle + coupling audit
```

Verify the archived evidence without trusting the summary:

```bash
python scripts/verify_evidence_bundle.py        # checksums -> hash chain -> manifest -> recompute
python scripts/audit_independent_recompute.py   # statistics from scratch, no project imports
```

Re-run the formal experiment (writes to a *new* directory, never overwrites the
reference artifacts):

```bash
python scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2_rerun
```

---

## Protocol and evidence anchors

| Item | Value |
|---|---|
| Protocol | `docs/PROTOCOL-frozen-v2.md` (frozen before the v2 run) |
| Protocol body SHA-256 | `205ecf9ff156d003887502f438dc4975bcd3a9b3e85b4a2c70feb54eea8a5137` |
| Whole-file SHA-256 | `0a0ac56daad4257c2a7542bcf7a4d50afe0317513a54a9fa7616eceb9054cde1` |
| Evidence bundle | `evidence/gateE-v2p1-full.tar.gz` + `evidence/gateE-v1-holdout-summaries.tar.gz` + `SHA256SUMS` |

The protocol hash is verifiable **without git**: it is computed over the file
body up to the `<!-- SIGNATURE -->` line. See `docs/PROTOCOL-v2.freeze.json`.

---

## Public history disclosure

This public repository is a **privacy-scrubbed snapshot** with a **single curated
commit**. It is not the incremental development history. Absolute local home
paths were replaced with `<LOCAL_HOME>`; no scientific content, result, commit
message or number was altered. Each file's SHA-256 is in
`PUBLIC_MANIFEST.json`, and the per-file redaction log is in `PUBLIC_RELEASE.md`.

---

## Licence

Apache-2.0. Third-party attributions in `NOTICE`.

## Citation

See `CITATION.cff`.
