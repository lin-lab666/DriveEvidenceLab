"""Demo 4 — Programmatic integration with the Python SDK.

Shows how another Python project would call DriveEvidenceLab and consume its
results as *structured data*: batch-run scenarios, collect typed result
objects, filter failures, and flatten everything into plain dictionaries ready
for pandas / csv / your own analysis stack.  No CLI, no files, no globals.

Run from anywhere once the package is installed:

    python examples/programmatic_integration_demo.py
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from driveevidence.scenario import ScenarioIR
from driveevidence.sim import EpisodeResult, create_adapter
from driveevidence.stats import cohens_h, wilson_ci

# ---------------------------------------------------------------------------
# 1. Your own scenarios as plain dicts — no file I/O required.
#    This is the canonical scenario IR (ir/v1).
# ---------------------------------------------------------------------------
SCENARIOS: List[Dict[str, Any]] = [
    {
        "ir_version": "ir/v1",
        "scenario_id": "cruise_free_road",
        "road": {"type": "straight", "road_length_m": 500.0, "lanes": 3,
                 "lane_width_m": 3.7, "speed_limit_mps": 33.0},
        "ego": {"id": "ego", "x_m": 50.0, "y_m": 1.85, "v_mps": 25.0,
                "heading_rad": 0.0, "length_m": 4.5, "width_m": 1.8, "kind": "car"},
        "vehicles": [],
        "odd": {},
        "meta": {"description": "ego cruises alone — should never fail"},
    },
    {
        "ir_version": "ir/v1",
        "scenario_id": "tailgate_slow_lead",
        "road": {"type": "straight", "road_length_m": 500.0, "lanes": 3,
                 "lane_width_m": 3.7, "speed_limit_mps": 33.0},
        "ego": {"id": "ego", "x_m": 50.0, "y_m": 1.85, "v_mps": 28.0,
                "heading_rad": 0.0, "length_m": 4.5, "width_m": 1.8, "kind": "car"},
        "vehicles": [{"id": "v1", "x_m": 70.0, "y_m": 1.85, "v_mps": 10.0,
                      "heading_rad": 0.0, "length_m": 4.5, "width_m": 1.8, "kind": "car"}],
        "odd": {},
        "meta": {"description": "fast ego, slow lead — expected collision"},
    },
]


def main() -> int:
    print("=" * 64)
    print("DriveEvidenceLab — programmatic integration demo")
    print("=" * 64)

    adapter = create_adapter("builtin")

    # ------------------------------------------------------------------
    # 2. Batch-run your scenarios and keep the typed result objects.
    # ------------------------------------------------------------------
    results = []
    for spec in SCENARIOS:
        scenario = ScenarioIR.from_dict(spec)
        result = adapter.run_episode(scenario, seed=123, planner_name="safe_follow",
                                     config={"max_steps": 80})
        results.append((scenario, result))
        print(f"\n{scenario.scenario_id}:")
        print(f"  category : {result.failure_category.value}")
        print(f"  detail   : {result.failure_detail}")
        print(f"  steps    : {result.steps}  (dt=0.1s, max_steps=80)")
        print(f"  metrics  : { {k: round(v, 3) for k, v in result.metrics.items()} }")

    # ------------------------------------------------------------------
    # 3. Flatten to plain dicts — the hand-off format for pandas / csv.
    # ------------------------------------------------------------------
    rows: List[Dict[str, Any]] = []
    for scenario, r in results:
        row = {
            "scenario_id": scenario.scenario_id,
            "scenario_hash": scenario.scenario_hash,
            "adapter": f"{r.adapter_name}/{r.adapter_version}",
            "planner": r.planner_name,
            "seed": r.seed,
            "category": r.failure_category.value,
            "steps": r.steps,
            **{f"metric_{k}": v for k, v in r.metrics.items()},
        }
        rows.append(row)

    print("\nflat records (ready for pandas.DataFrame(rows)):")
    for row in rows:
        print(f"  {row['scenario_id']:<20} {row['category']:<10} "
              f"min_gap={row['metric_min_gap_m']:.2f}m  min_ttc={row['metric_min_ttc_s']:.3f}s")

    # ------------------------------------------------------------------
    # 4. Statistics on your own batch results.
    # ------------------------------------------------------------------
    # "collision" is a safety failure; "timeout" merely means the episode
    # ended without one — the framework reports categories, you interpret them.
    n_collision = sum(1 for _, r in results if r.failure_category.value == "collision")
    if results:
        lo, hi = wilson_ci(n_collision, len(results))
        print(f"\ncollision rate over your batch: {n_collision}/{len(results)} "
              f"[Wilson 95% CI: {lo:.4f}, {hi:.4f}]")

    failures = [r for _, r in results if r.failure_category == "collision"]
    print(f"collision episodes retained for further analysis: {len(failures)}")
    print("each EpisodeResult carries .trajectory (t/x/y/v/heading) so you can "
          "plot or post-process without re-simulating.")

    print("\nIntegration summary: DriveEvidenceLab returns typed, hash-stamped "
          "result objects — drop them straight into your existing test pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
