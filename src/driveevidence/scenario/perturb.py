"""Seed-derived epsilon-perturbation of scenario initial conditions.

Motivation
----------
A holdout protocol that only varies a *seed* is meaningless for a simulator
that does not consume the seed: every "replication" is a bit-identical rerun
of the same deterministic function, so any observed stability is true by
construction rather than by measurement.

This module makes the seed semantically meaningful at the *scenario* level.
Given a canonical :class:`~driveevidence.scenario.ir.ScenarioIR` and an integer
seed, it returns a scenario drawn from a bounded epsilon-neighbourhood of the
original initial conditions. Repeating an episode over several perturbation
seeds therefore answers the question the protocol actually intends:

    "Does the observed failure survive small variations of the initial
    conditions, or is it a knife-edge artifact of one exact configuration?"

The perturbation is:

* **deterministic** - identical (scenario, seed) always yields an identical
  scenario, including across processes and machines;
* **structure preserving** - lane count, road geometry, vehicle count and
  vehicle ids are never modified, so failure categories remain comparable;
* **bounded** - every displacement is drawn uniformly from ``[-band, +band]``
  and longitudinal gaps are additionally floored to avoid creating physically
  impossible overlapping spawns;
* **explicitly separate from the search RNG** - the perturbation stream uses
  ``SeedSequence(entropy=[seed, salt])`` so that it cannot be confused with
  the sampler's own stream.

This module does not validate the result; callers must call
``scenario.validate()`` and treat a ``ScenarioValidationError`` as
``INFEASIBLE`` exactly as they would for a sampled scenario.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

from driveevidence.scenario.ir import ScenarioIR, VehicleState

# Fixed salt keeps perturbation streams disjoint from any other RNG derived
# from the same integer seed. Changing this value invalidates comparability
# with previously archived perturbations, so it is versioned below.
PERTURBATION_SALT = 0x9E3779B9
PERTURBATION_SCHEME = "eps-perturb/1.0"


@dataclass(frozen=True)
class PerturbationBands:
    """Half-widths of the uniform perturbation applied to each quantity.

    Attributes:
        ego_speed_mps: Uniform jitter on ego longitudinal speed.
        ego_lateral_m: Uniform jitter on ego lateral offset.
        lead_gap_m: Uniform jitter on each other vehicle's longitudinal offset.
        lead_speed_mps: Uniform jitter on each other vehicle's speed.
        min_gap_m: Lower bound enforced on the bumper-to-bumper longitudinal
            gap between ego and any other vehicle after perturbation.
    """

    ego_speed_mps: float = 2.0
    ego_lateral_m: float = 0.15
    lead_gap_m: float = 3.0
    lead_speed_mps: float = 1.5
    min_gap_m: float = 2.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "ego_speed_mps": self.ego_speed_mps,
            "ego_lateral_m": self.ego_lateral_m,
            "lead_gap_m": self.lead_gap_m,
            "lead_speed_mps": self.lead_speed_mps,
            "min_gap_m": self.min_gap_m,
        }


DEFAULT_PERTURBATION_BANDS = PerturbationBands()


def _rng_for(seed: int, salt: int) -> np.random.Generator:
    """Build a generator whose stream is determined solely by (seed, salt)."""
    return np.random.default_rng(
        np.random.SeedSequence(entropy=[int(seed) & 0xFFFFFFFFFFFFFFFF, int(salt)])
    )


def perturb_scenario(
    scenario: ScenarioIR,
    seed: int,
    bands: PerturbationBands = DEFAULT_PERTURBATION_BANDS,
    salt: int = PERTURBATION_SALT,
) -> ScenarioIR:
    """Return a scenario in the bounded epsilon-neighbourhood of ``scenario``.

    Args:
        scenario: Source scenario. Not modified.
        seed: Perturbation seed. Different seeds give different neighbourhood
            draws; the same seed always gives the same draw.
        bands: Half-widths of the uniform perturbation.
        salt: Stream salt, see :data:`PERTURBATION_SALT`.

    Returns:
        A new :class:`ScenarioIR` with the same ids, lane geometry and vehicle
        count, but jittered initial conditions. The original ``scenario_id`` is
        preserved and a ``perturbation`` record is added to ``meta`` for
        provenance.
    """
    rng = _rng_for(seed, salt)

    def u(band: float) -> float:
        if band <= 0.0:
            return 0.0
        return float(rng.uniform(-band, band))

    ego_src = scenario.ego
    ego = VehicleState(
        id=ego_src.id,
        x_m=ego_src.x_m,  # longitudinal start position is part of the scenario identity
        y_m=ego_src.y_m + u(bands.ego_lateral_m),
        v_mps=max(0.0, ego_src.v_mps + u(bands.ego_speed_mps)),
        heading_rad=ego_src.heading_rad,
        length_m=ego_src.length_m,
        width_m=ego_src.width_m,
        kind=ego_src.kind,
    )

    others: List[VehicleState] = []
    for v in scenario.vehicles:
        # Longitudinal jitter is applied as a gap so that ordering and
        # non-overlap can be enforced against ego.
        raw_gap = v.x_m - ego_src.x_m
        jittered_gap = max(
            bands.min_gap_m + (ego_src.length_m + v.length_m) / 2.0,
            raw_gap + u(bands.lead_gap_m),
        )
        others.append(
            VehicleState(
                id=v.id,
                x_m=ego_src.x_m + jittered_gap,
                y_m=v.y_m,
                v_mps=max(0.0, v.v_mps + u(bands.lead_speed_mps)),
                heading_rad=v.heading_rad,
                length_m=v.length_m,
                width_m=v.width_m,
                kind=v.kind,
            )
        )

    meta: Dict[str, Any] = dict(scenario.meta)
    meta["perturbation"] = {
        "scheme": PERTURBATION_SCHEME,
        "seed": int(seed),
        "salt": int(salt),
        "bands": bands.to_dict(),
        "source_scenario_hash": scenario.scenario_hash,
    }

    return ScenarioIR(
        scenario_id=scenario.scenario_id,
        road_length_m=scenario.road_length_m,
        lanes=scenario.lanes,
        lane_width_m=scenario.lane_width_m,
        speed_limit_mps=scenario.speed_limit_mps,
        ego=ego,
        vehicles=others,
        odd=dict(scenario.odd),
        meta=meta,
        ir_version=scenario.ir_version,
    )


def perturbation_seeds(seed_pool: List[int], index: int, n: int) -> List[int]:
    """Deterministically assign ``n`` distinct seeds from ``seed_pool``.

    Candidate ``index`` receives ``pool[(index + k) % len(pool)]`` for
    ``k in range(n)``, so consecutive candidates rotate through the pool
    instead of all sharing the first ``n`` seeds. This keeps per-candidate
    replication independent while bounding the global seed budget.
    """
    if not seed_pool:
        raise ValueError("seed_pool must not be empty")
    if n <= 0:
        raise ValueError("n must be positive")
    if n > len(seed_pool):
        raise ValueError("cannot draw %d distinct seeds from a pool of %d" % (n, len(seed_pool)))
    return [seed_pool[(index + k) % len(seed_pool)] for k in range(n)]
