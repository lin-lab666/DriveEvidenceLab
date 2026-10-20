#!/usr/bin/env python3
"""Generate the publication figures for the DriveEvidenceLab README.

Every figure is rendered from REAL archived artifacts in
``runs/formal_experiment_v2p1/`` (the protocol v2.1 results) — nothing is
synthesised or hand-edited.  The script is deterministic and re-runnable:

    PYTHONPATH=src python scripts/make_figures.py --out docs/_figures

Figures produced (all PNG):

  1. ``trajectory_collision.png``  ego vs lead-vehicle longitudinal position
     for a real archived collision episode, with the collision point marked.
  2. ``gap_and_speed.png``         gap (bumper-to-bumper) and ego speed over
     time for the same episode, annotated with the collision time.
  3. ``search_comparison.png``     random vs mutation: discovery yield and
     stable yield with 95% Wilson intervals (v2.1 headline numbers).
  4. ``evidence_pipeline.png``     a schematic of the evidence-chain flow
     (explicitly labelled as a diagram, not a measurement).

Data sources are printed to stdout and embedded in each PNG via metadata, and
a ``sources.json`` manifest is written next to the figures so a reader can
trace every number back to its origin.

This script needs only numpy + matplotlib (the ``stats`` extra provides scipy,
which is NOT required here).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driveevidence.stats import wilson_ci  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "formal_experiment_v2p1"

def _v2p1_numbers(run_dir: Path):
    """Read the headline numbers from the run's own summary.json.

    The v2.1 summary records, per method, the discovery counts and the
    holdout stable counts; this keeps the figure from silently drifting if
    the run is ever regenerated.
    """
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    stats = summary["statistics"]
    out = {}
    for method in ("random", "mutation"):
        b = stats[method]
        out[method] = {
            "discovery_yield": b["discovery_yield"],
            "discovery_hits": b["discovery_failures"],
            "discovery_denom": b["total_launched"],
            "tested": b["tested_candidates"],
            "stable": b["stable_candidates"],
            "stable_yield": b["stable_yield"],
        }
    return out


def _load_episodes():
    """Load every archived episode, keyed by a stable sort."""
    eps = []
    for p in sorted((RUN_DIR / "episodes").glob("*.json")):
        eps.append((json.loads(p.read_text(encoding="utf-8")), p))
    return eps


def _pick_collision(eps):
    """Return (episode_dict, path) for a clean short collision episode."""
    for e, e_path in eps:
        r = e["result"]
        if r["failure_category"] == "collision" and r["failure_detail"].startswith("collision with vehicle"):
            traj = r["trajectory"]
            if len(traj) >= 4:
                return e, e_path
    raise SystemExit("no usable collision episode found")


def _lead_position(e, t):
    """Reconstruct the lead vehicle's longitudinal position at time t.

    The lead vehicle travels at constant speed (v_mps) in a straight line, so
    x_lead(t) = x_lead(0) + v_lead * t.  This is the same kinematic assumption
    the ``builtin`` simulator uses for non-ego vehicles.
    """
    lead = e["scenario"]["vehicles"][0]
    return lead["x_m"] + lead["v_mps"] * t


def fig_trajectory(eps, out: Path):
    e, e_path = _pick_collision(eps)
    r = e["result"]
    traj = r["trajectory"]
    t = [s["t"] for s in traj]
    ego_x = [s["x"] for s in traj]
    lead_x = [_lead_position(e, tt) for tt in t]
    # gap = lead bumper - ego bumper (both length 4.5 m)
    ego_length = e["scenario"]["ego"].get("length_m", 4.5)
    lead_length = e["scenario"]["vehicles"][0].get("length_m", 4.5)
    if ego_length != lead_length:
        raise SystemExit("gap formula assumes equal vehicle lengths; got "
                         f"ego={ego_length}, lead={lead_length}")
    gap = [lx - lead_length - (ex) for lx, ex in zip(lead_x, ego_x)]

    fig, ax = plt.subplots(figsize=(8.4, 4.4), dpi=130)
    ax.plot(t, ego_x, label="ego (rear, approaching)", color="#c0392b", lw=2)
    ax.plot(t, lead_x, label="lead vehicle (front)", color="#2471a3", lw=2, ls="--")
    # collision time = last sample where gap <= 0
    hit_idx = next((i for i, g in enumerate(gap) if g <= 0), len(gap) - 1)
    if hit_idx < len(t):
        ax.axvline(t[hit_idx], color="#7f8c8d", lw=1, ls=":")
        ax.annotate(
            f"collision\nt={t[hit_idx]:.2f}s",
            xy=(t[hit_idx], ego_x[hit_idx]),
            xytext=(t[hit_idx] - 0.28, ego_x[hit_idx] - 9),
            fontsize=9,
        )
    ax.set_xlabel("time (s)")
    ax.set_ylabel("longitudinal position x (m)")
    ax.set_title(f"Failure trajectory — {r['scenario_id']} ({r['failure_category']})")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, metadata={"Source": "runs/formal_experiment_v2p1/episodes/*.json"})
    plt.close(fig)
    return {"figure": out.name, "episode": r["scenario_id"],
            "archive_file": e_path.name,
            "source": "runs/formal_experiment_v2p1/episodes/*.json (archived trajectory)"}


def fig_gap_speed(eps, out: Path):
    e, e_path = _pick_collision(eps)
    r = e["result"]
    traj = r["trajectory"]
    t = [s["t"] for s in traj]
    ego_x = [s["x"] for s in traj]
    lead_x = [_lead_position(e, tt) for tt in t]
    lead_length = e["scenario"]["vehicles"][0].get("length_m", 4.5)
    gap = [lx - lead_length - ex for lx, ex in zip(lead_x, ego_x)]
    v = [s["v"] for s in traj]

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.4, 4.8), dpi=130, sharex=True)
    a1.plot(t, gap, color="#c0392b", lw=2)
    a1.axhline(0, color="#7f8c8d", lw=1, ls=":")
    a1.set_ylabel("gap to lead (m)")
    a1.set_title("Bumper-to-bumper gap collapses to a collision")
    a1.grid(alpha=0.3)
    a2.plot(t, v, color="#2471a3", lw=2)
    a2.set_xlabel("time (s)")
    a2.set_ylabel("ego speed (m/s)")
    a2.set_title("Ego speed over the same episode")
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, metadata={"Source": "runs/formal_experiment_v2p1/episodes/*.json"})
    plt.close(fig)
    return {"figure": out.name, "episode": r["scenario_id"],
            "archive_file": e_path.name,
            "source": "runs/formal_experiment_v2p1/episodes/*.json (archived trajectory)"}


def fig_search(numbers, out: Path):
    """Random vs mutation: discovery + stable yield with Wilson 95% CI."""
    methods = [("Random Search", numbers["random"]), ("Mutation Search", numbers["mutation"])]
    labels = [m for m, _ in methods]
    disc = [d["discovery_yield"] for _, d in methods]
    disc_ci = [wilson_ci(d["discovery_hits"], d["discovery_denom"]) for _, d in methods]
    stable = [d["stable_yield"] for _, d in methods]
    stable_ci = [wilson_ci(d["stable"], d["tested"]) for _, d in methods]

    x = range(len(methods))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 4.0), dpi=130)

    for ax, vals, cis, title in [
        (a1, disc, disc_ci, "Discovery yield\n(failures per episode)"),
        (a2, stable, stable_ci, "Stable failure yield\n(ε-perturbation holdout)"),
    ]:
        ax.bar(list(x), vals, width=0.55, color=["#c0392b", "#2471a3"])
        for xi, (v, (lo, hi)) in zip(x, zip(vals, cis)):
            ax.errorbar(xi, v, yerr=[[v - lo], [hi - v]], fmt="none", color="#2c3e50", lw=1.5, capsize=6)
            ax.text(xi, v + 0.02, f"{v:.3f}", ha="center", fontsize=10)
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_ylim(0, 1.05)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Protocol v2.1 — `builtin/1.1`, 64 paired seeds (n=8192 discovery episodes)",
                 fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out, metadata={"Source": "runs/formal_experiment_v2p1/summary.json"})
    plt.close(fig)
    return {
        "figure": out.name,
        "source": "runs/formal_experiment_v2p1/summary.json (read directly by make_figures.py; independently recomputed by scripts/verify_evidence_bundle.py)",
        "random": dict(numbers["random"]),
        "mutation": dict(numbers["mutation"]),
    }


def fig_pipeline(out: Path):
    """A schematic of the evidence-chain flow (diagram, not a measurement)."""
    fig, ax = plt.subplots(figsize=(9.6, 3.2), dpi=130)
    ax.axis("off")
    steps = [
        "Scenario IR\n(ir/v1 + hash)",
        "Search\n(budgeted)",
        "Simulate\n(builtin/1.1)",
        "Detect failure\n(category)",
        "Evidence\n(hash chain)",
        "Replay\n(byte-level)",
        "Audit\n(T1/T2/T3)",
    ]
    n = len(steps)
    for i, s in enumerate(steps):
        x = i / (n - 1)
        ax.add_patch(plt.Rectangle((x - 0.055, 0.35), 0.11, 0.30, fc="#ecf0f1", ec="#34495e", lw=1))
        ax.text(x, 0.5, s, ha="center", va="center", fontsize=7.5)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch((x + 0.058, 0.5), (x + 0.088, 0.5),
                                         arrowstyle="-|>", mutation_scale=12, color="#34495e"))
    ax.text(0.5, 0.12, "Schematic diagram — not a measurement of any physical quantity.",
            ha="center", fontsize=8, style="italic", color="#7f8c8d")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(0, 0.75)
    fig.tight_layout()
    fig.savefig(out, metadata={"Source": "schematic (illustrative)"})
    plt.close(fig)
    return {"figure": out.name, "source": "schematic (illustrative, labelled as such)"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="docs/_figures", help="output directory")
    ap.add_argument("--run", default=str(RUN_DIR), help="v2.1 run directory")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    eps = _load_episodes()
    if not eps:
        raise SystemExit(f"no episodes under {RUN_DIR}/episodes")

    numbers = _v2p1_numbers(Path(args.run))
    sources = {}
    sources["trajectory_collision"] = fig_trajectory(eps, out / "trajectory_collision.png")
    sources["gap_and_speed"] = fig_gap_speed(eps, out / "gap_and_speed.png")
    sources["search_comparison"] = fig_search(numbers, out / "search_comparison.png")
    sources["evidence_pipeline"] = fig_pipeline(out / "evidence_pipeline.png")

    (out / "sources.json").write_text(
        json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    for name, meta in sources.items():
        print(f"[ok] {meta['figure']}  <- {meta['source']}")
    print(f"manifest: {out / 'sources.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
