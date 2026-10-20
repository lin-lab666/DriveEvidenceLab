#!/usr/bin/env python
"""Record the feasibility of a third-party dynamics engine for protocol v3.

This script deliberately does **not** run any experiment.  It only records what
is installed, which versions, what license the package declares, and whether a
deterministic replay is even possible.  That is the input to
``docs/PROTOCOL-v3-draft.md`` §6 (preconditions before freezing).

Writing this down mechanically matters: "we considered SUMO" is a claim, an
install log with versions and license strings is evidence.

Usage:
    python scripts/probe_v3_engine.py [--out runs/v3_feasibility.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

CANDIDATES = [
    # module name, what it would provide, is it truly third-party dynamics?
    ("sumo", "microscopic traffic simulator with Krauss car-following", True),
    ("traci", "SUMO control interface", True),
    ("commonroad_vehicle_models", "single-track / point-mass vehicle models", True),
    ("carla", "Unreal-based closed-loop simulator", True),
    ("highway_env", "kinematic RL environment (already integrated)", False),
    ("commonroad", "scenario exchange and judging (already integrated)", False),
]


def module_info(name: str) -> Dict[str, Any]:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return {"installed": False}
    info: Dict[str, Any] = {"installed": True, "origin": str(spec.origin)}
    try:
        from importlib.metadata import version, metadata

        info["version"] = version(name)
        meta = metadata(name)
        info["license"] = meta.get("License") or ""
        info["license_expression"] = meta.get("License-Expression") or ""
        info["requires_python"] = meta.get("Requires-Python") or ""
    except Exception as exc:  # noqa: BLE001 - metadata is best-effort
        info["metadata_error"] = f"{type(exc).__name__}: {exc}"
    return info


def find_binary(names: list[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in names:
        path = shutil.which(name)
        out[name] = path
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/v3_feasibility.json")
    args = ap.parse_args()

    engines = []
    for name, provides, independent in CANDIDATES:
        info = module_info(name)
        info.update({"module": name, "provides": provides, "independent_dynamics": independent})
        engines.append(info)

    result = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "engines": engines,
        "binaries": find_binary(["sumo", "sumo-gui", "netconvert", "duarouter"]),
    }

    installed_independent = [
        e["module"]
        for e in engines
        if e.get("installed") and e.get("independent_dynamics")
    ]
    result["verdict"] = {
        "independent_engine_available": bool(installed_independent),
        "installed": installed_independent,
        "gate_d_status": "PARTIAL (unchanged — v3 not frozen, no confirmatory run)",
        "note": (
            "Availability is necessary but not sufficient: protocol v3 §6 requires a "
            "determinism check, a scenario-mapping fidelity table and a failure-criterion "
            "alignment table before any confirmatory comparison may run."
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"wrote {out}")
    for e in engines:
        state = f"installed {e.get('version', '?')}" if e.get("installed") else "-"
        flag = "independent" if e["independent_dynamics"] else "not independent"
        print(f"  {e['module']:28s} {state:22s} ({flag})")
    print()
    print(
        "independent dynamics engine available:",
        "YES -> " + ", ".join(installed_independent)
        if installed_independent
        else "NO",
    )
    print("gate D:", result["verdict"]["gate_d_status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
