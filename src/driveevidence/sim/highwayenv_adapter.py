"""HighwayEnv adapter for DriveEvidenceLab.

IMPORTANT HONESTY NOTE: HighwayEnv uses its own internal coordinate
system and vehicle initialization. This adapter maps the canonical IR
to HighwayEnv's config API (lanes_count, vehicles_count, speed limit,
etc.) but CANNOT guarantee exact placement of every IR vehicle. The
scenario_hash is preserved for traceability; however, the actual
simulated layout is a config-approximation of the IR.

Cross-adapter comparisons MUST therefore only use metrics/semantics
that are supported and comparable between backends.
"""
from __future__ import annotations

import time
import warnings
from typing import Any, Dict, List, Optional

import numpy as np

from driveevidence.scenario.ir import ScenarioIR
from driveevidence.sim.base import (
    EpisodeResult,
    FailureCategory,
    SimulatorAdapter,
    TrajectorySample,
    register_adapter,
)

try:
    import gymnasium as gym
    import highway_env
except Exception as exc:  # pragma: no cover
    gym = None  # type: ignore
    highway_env = None  # type: ignore
    _IMPORT_ERROR = str(exc)
else:
    _IMPORT_ERROR = ""


@register_adapter
class HighwayEnvAdapter(SimulatorAdapter):
    """Adapter using the real highway-env gymnasium environment.

    Supported scenario subset: straight multi-lane highway; exact spawn
    positions are approximate.
    """

    name = "highwayenv"
    version = "unknown"

    def __init__(self) -> None:
        if gym is None or highway_env is None:
            raise RuntimeError(f"highway-env not available: {_IMPORT_ERROR}")
        self.version = getattr(highway_env, "__version__", "unknown")

    def capabilities(self) -> Dict[str, bool]:
        return {
            "collision": True,
            "off_road": True,
            "rule_violation": False,  # not detected explicitly in this adapter
            "near_miss": False,
            "timeout": True,
            "deterministic_replay": True,
        }

    def _make_env(self, scenario: ScenarioIR, config: Dict[str, Any]):
        # Determine action configuration empirically by creating a throw-away env.
        # We prefer purely longitudinal actions to keep the planner simple.
        action_cfg = config.get("action", {"type": "DiscreteMetaAction"})
        env = gym.make(
            config.get("env_id", "highway-v0"),
            config={
                "lanes_count": scenario.lanes,
                "vehicles_count": len(scenario.vehicles),
                "duration": config.get("duration", 10),
                "simulation_frequency": 15,
                "policy_frequency": config.get("policy_frequency", 5),
                "initial_speed": float(scenario.ego.v_mps),
                "speed_limit": float(scenario.speed_limit_mps),
                "action": action_cfg,
                "offroad_terminal": True,
                "collision_reward": -1.0,
                "offroad_terminal": True,
            },
            render_mode=None,
        )
        return env

    def _choose_action(self, env, observation, scenario: ScenarioIR) -> int:
        """Heuristic longitudinal policy.

        We introspect the action type and select acceleration / slower /
        maintain if available, otherwise fall back to discrete action 1
        (straight) for DiscreteAction or IDLE for DiscreteMetaAction.
        """
        # Try to access unwrapped action type
        action_type = getattr(env.unwrapped, "action_type", None)
        if action_type is None:
            return 1  # safe fallback
        actions = getattr(action_type, "available_actions", None)
        if actions is None:
            # inspect action space size and pick middle index as "maintain"
            return min(1, env.action_space.n - 1) if hasattr(env.action_space, "n") else 0

        # Map semantics to indices if labels are strings
        if isinstance(actions, dict):
            labels = {str(k).upper(): v for k, v in actions.items()}
            if "SLOWER" in labels:
                return labels["SLOWER"]
            if "FASTER" in labels:
                return labels["FASTER"]
            if "IDLE" in labels:
                return labels["IDLE"]
            return next(iter(actions.values()))

        # If actions is a list of ints, use first maintain-like index
        if isinstance(actions, (list, tuple)) and len(actions):
            return actions[len(actions) // 2]
        return 1

    def run_episode(
        self,
        scenario: ScenarioIR,
        seed: int,
        planner_name: str = "default",
        config: Optional[Dict[str, Any]] = None,
    ) -> EpisodeResult:
        config = config or {}
        env = self._make_env(scenario, config)
        env.reset(seed=seed)

        max_steps = int(config.get("max_steps", 50))
        trajectory: List[TrajectorySample] = []
        category = FailureCategory.NONE
        detail = ""
        steps = 0
        metrics = {"min_gap_m": -1.0, "min_ttc_s": -1.0, "max_v_mps": 0.0, "final_x_m": 0.0}

        start_wall = time.perf_counter()
        obs, info = env.reset(seed=seed)
        ego_vehicle = getattr(env.unwrapped, "vehicle", None)
        road = getattr(env.unwrapped, "road", None)
        sim_version = getattr(env.unwrapped, "__module__", "highway_env")

        for step in range(max_steps):
            # sample trajectory from ego vehicle
            if ego_vehicle is not None:
                x = float(getattr(ego_vehicle, "position", [0.0, 0.0])[0])
                y = float(getattr(ego_vehicle, "position", [0.0, 0.0])[1])
                v = float(getattr(ego_vehicle, "speed", 0.0))
                heading = float(getattr(ego_vehicle, "heading", 0.0))
                trajectory.append(TrajectorySample(t=step * 0.05, x=x, y=y, v=v, heading=heading))
                metrics["max_v_mps"] = max(metrics["max_v_mps"], v)
                metrics["final_x_m"] = x
            else:
                trajectory.append(TrajectorySample(t=step * 0.05, x=0.0, y=0.0, v=0.0, heading=0.0))

            action = self._choose_action(env, obs, scenario)
            obs, reward, terminated, truncated, info = env.step(action)
            steps = step + 1

            if terminated or truncated:
                crashed = info.get("crashed", False) or info.get("collision", False)
                # Highway-env "terminated" also fires for off-road if configured.
                offroad = info.get("off_road", False)
                if crashed:
                    category = FailureCategory.COLLISION
                    detail = "highway-env reported crash"
                elif offroad:
                    category = FailureCategory.OFF_ROAD
                    detail = "highway-env reported off-road"
                elif truncated:
                    category = FailureCategory.TIMEOUT
                    detail = f"reached max_steps {max_steps} (env truncated)"
                else:
                    category = FailureCategory.UNKNOWN
                    detail = "episode ended without recognized failure"
                break
        else:
            category = FailureCategory.TIMEOUT
            detail = f"reached max_steps {max_steps}"

        wall_time_s = time.perf_counter() - start_wall
        env.close()

        return EpisodeResult(
            scenario_id=scenario.scenario_id,
            scenario_hash=scenario.scenario_hash,
            adapter_name=self.name,
            adapter_version=self.version,
            planner_name=planner_name,
            seed=seed,
            steps=steps,
            wall_time_s=wall_time_s,
            terminated=category
            in {FailureCategory.COLLISION, FailureCategory.OFF_ROAD},
            truncated=category
            in {FailureCategory.TIMEOUT, FailureCategory.NEAR_MISS},
            failure_category=category,
            failure_detail=detail,
            trajectory=trajectory,
            metrics=metrics,
            raw={
                "env_id": config.get("env_id", "highway-v0"),
                "approximation_warning": (
                    "IR vehicle positions are approximated by highway-env's internal "
                    "initialization; exact placement is not supported by this adapter."
                ),
            },
        )
