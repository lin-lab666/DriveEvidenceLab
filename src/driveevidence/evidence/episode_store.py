"""Episode storage: scenario + result round-trip for evidence packages."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterator, Optional, Tuple

from driveevidence.scenario.ir import ScenarioIR
from driveevidence.sim.base import EpisodeResult


class EpisodeStore:
    """Filesystem-backed episode archive inside a run directory."""

    SUBDIR = "episodes"

    def __init__(self, run_dir: str):
        self.run_dir = os.path.abspath(run_dir)
        self.episodes_dir = os.path.join(self.run_dir, self.SUBDIR)
        os.makedirs(self.episodes_dir, exist_ok=True)

    def _next_seq(self) -> int:
        max_seq = 0
        if not os.path.isdir(self.episodes_dir):
            return 1
        for name in os.listdir(self.episodes_dir):
            m = re.match(r"(\d+)\.json$", name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        return max_seq + 1

    def save(
        self,
        scenario: ScenarioIR,
        result: EpisodeResult,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        seq = self._next_seq()
        filename = f"{seq:04d}.json"
        path = os.path.join(self.episodes_dir, filename)
        payload = {
            "scenario": scenario.to_dict(),
            "result": result.to_dict(),
            "extra": extra or {},
            "saved_at": _now(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        return path

    def load(self, seq: int) -> Tuple[ScenarioIR, EpisodeResult, Dict[str, Any]]:
        path = os.path.join(self.episodes_dir, f"{seq:04d}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"episode {seq:04d} not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            ScenarioIR.from_dict(data["scenario"]),
            EpisodeResult.from_dict(data["result"]),
            data.get("extra", {}),
        )

    def iter_all(self) -> Iterator[Tuple[int, ScenarioIR, EpisodeResult, Dict[str, Any]]]:
        if not os.path.isdir(self.episodes_dir):
            return
        for name in sorted(os.listdir(self.episodes_dir)):
            m = re.match(r"(\d+)\.json$", name)
            if not m:
                continue
            seq = int(m.group(1))
            scenario, result, extra = self.load(seq)
            yield seq, scenario, result, extra

    @staticmethod
    def replay_kwargs(episode_data: Dict[str, Any]) -> Dict[str, Any]:
        """Recover the exact execution configuration needed for a faithful replay.

        The adapter configuration (``dt``, ``max_steps``, ...) must be restored
        from the archived result, otherwise a replay silently falls back to the
        adapter defaults and produces a different episode (for example a
        ``max_steps=80`` run replayed at the default 300 steps changes
        ``final_x_m`` and the step count). This was a real defect found by
        ``scripts/audit_scientific_validity.py``; see docs/DECISIONS.md D014.
        """
        result = episode_data.get("result", {}) or {}
        raw = result.get("raw", {}) or {}
        config: Dict[str, Any] = {}

        nested = raw.get("config")
        if isinstance(nested, dict):
            config.update(nested)

        # Adapters record their effective configuration as top-level keys.
        for key in ("dt", "max_steps", "rule_speed_tolerance_mps",
                    "near_miss_gap_m", "near_miss_ttc_s"):
            if key in raw:
                config[key] = raw[key]

        extra = episode_data.get("extra", {}) or {}
        if isinstance(extra.get("config"), dict):
            config.update(extra["config"])

        return {
            "seed": result.get("seed"),
            "planner_name": result.get("planner_name", "default"),
            "config": config,
        }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
