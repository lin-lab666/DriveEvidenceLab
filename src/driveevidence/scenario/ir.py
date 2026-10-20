"""Canonical scenario intermediate representation (IR v1).

Units are fixed: meters (m), seconds (s), meters/second (m/s), radians (rad).
Frame convention: x is forward along the road direction, y is lateral
(left positive). All scenarios are expressed on a straight-lane road
("straight" road type) in IR v1; curves are UNSUPPORTED and must be
rejected by validate().
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

IR_VERSION = "ir/v1"

_ALLOWED_ODD_KEYS = {"weather", "time_of_day", "surface", "visibility_m"}
_ALLOWED_VEHICLE_KINDS = {"car", "truck", "bus", "motorcycle", "bicycle", "pedestrian"}


class ScenarioValidationError(ValueError):
    """Raised when a scenario violates IR v1 validity constraints."""


@dataclass
class VehicleState:
    id: str
    x_m: float
    y_m: float
    v_mps: float
    heading_rad: float
    length_m: float = 4.5
    width_m: float = 1.8
    kind: str = "car"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "x_m": self.x_m, "y_m": self.y_m, "v_mps": self.v_mps,
            "heading_rad": self.heading_rad, "length_m": self.length_m,
            "width_m": self.width_m, "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VehicleState":
        return cls(**d)


@dataclass
class ScenarioIR:
    """Canonical, versioned, deterministically-hashable scenario."""

    scenario_id: str
    road_length_m: float
    lanes: int
    lane_width_m: float
    speed_limit_mps: float
    ego: VehicleState
    vehicles: List[VehicleState] = field(default_factory=list)
    odd: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    ir_version: str = IR_VERSION

    # ---------- serialization ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ir_version": self.ir_version,
            "scenario_id": self.scenario_id,
            "road": {
                "type": "straight",
                "road_length_m": self.road_length_m,
                "lanes": self.lanes,
                "lane_width_m": self.lane_width_m,
                "speed_limit_mps": self.speed_limit_mps,
            },
            "ego": self.ego.to_dict(),
            "vehicles": [v.to_dict() for v in self.vehicles],
            "odd": dict(self.odd),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioIR":
        if d.get("ir_version") != IR_VERSION:
            raise ScenarioValidationError(
                f"unsupported ir_version {d.get('ir_version')!r}, expected {IR_VERSION!r}")
        road = d["road"]
        if road.get("type") != "straight":
            raise ScenarioValidationError(
                f"road type {road.get('type')!r} is UNSUPPORTED in {IR_VERSION}")
        return cls(
            scenario_id=d["scenario_id"],
            road_length_m=road["road_length_m"],
            lanes=road["lanes"],
            lane_width_m=road["lane_width_m"],
            speed_limit_mps=road["speed_limit_mps"],
            ego=VehicleState.from_dict(d["ego"]),
            vehicles=[VehicleState.from_dict(v) for v in d.get("vehicles", [])],
            odd=dict(d.get("odd", {})),
            meta=dict(d.get("meta", {})),
        )

    # ---------- canonical encoding & hashing ----------
    def canonical_bytes(self) -> bytes:
        payload = json.dumps(self.to_dict(), sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False)
        return payload.encode("utf-8")

    @property
    def scenario_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    # ---------- validity constraints ----------
    def validate(self) -> None:
        """Raise ScenarioValidationError on any IR v1 violation.

        Scenario validity is INDEPENDENT of safety judgments (per SPEC:
        legality check != failure criteria). Overlapping spawns are
        INFEASIBLE scenarios (invalid), not collisions-to-be.
        """
        if not self.scenario_id or not isinstance(self.scenario_id, str):
            raise ScenarioValidationError("scenario_id must be a non-empty string")
        if self.road_length_m <= 0 or self.road_length_m > 10000:
            raise ScenarioValidationError(f"road_length_m out of range: {self.road_length_m}")
        if not (1 <= self.lanes <= 8):
            raise ScenarioValidationError(f"lanes out of range: {self.lanes}")
        if not (2.0 <= self.lane_width_m <= 5.0):
            raise ScenarioValidationError(f"lane_width_m out of range: {self.lane_width_m}")
        if not (0 < self.speed_limit_mps <= 60):
            raise ScenarioValidationError(f"speed_limit_mps out of range: {self.speed_limit_mps}")

        road_y_max = self.lanes * self.lane_width_m
        all_vs = [("ego", self.ego)] + [(v.id, v) for v in self.vehicles]
        seen_ids = set()
        for vid, v in all_vs:
            if vid in seen_ids:
                raise ScenarioValidationError(f"duplicate vehicle id: {vid}")
            seen_ids.add(vid)
            if not (-90.0 <= v.heading_rad <= 90.0):
                raise ScenarioValidationError(
                    f"{vid}: heading_rad {v.heading_rad} outside [-90, 90] (straight-road IR)")
            if not (0.0 <= v.v_mps <= 80.0):
                raise ScenarioValidationError(f"{vid}: v_mps {v.v_mps} outside [0, 80]")
            if not (0.5 <= v.length_m <= 25.0) or not (0.3 <= v.width_m <= 3.0):
                raise ScenarioValidationError(f"{vid}: vehicle size out of range")
            if v.kind not in _ALLOWED_VEHICLE_KINDS:
                raise ScenarioValidationError(f"{vid}: unknown kind {v.kind!r}")
            if v.x_m < 0 or v.x_m > self.road_length_m:
                raise ScenarioValidationError(f"{vid}: x_m {v.x_m} outside road")
            if abs(v.y_m) > road_y_max + 1e-6:
                raise ScenarioValidationError(
                    f"{vid}: |y_m| {abs(v.y_m)} exceeds road width {road_y_max}")

        # Spawn overlap => infeasible scenario (AABB approximation).
        boxes = [(vid, v) for vid, v in all_vs]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (id_i, vi), (id_j, vj) = boxes[i], boxes[j]
                dx = abs(vi.x_m - vj.x_m)
                dy = abs(vi.y_m - vj.y_m)
                if dx <= (vi.length_m + vj.length_m) / 2 and dy <= (vi.width_m + vj.width_m) / 2:
                    raise ScenarioValidationError(
                        f"spawn overlap between {id_i} and {id_j} (infeasible scenario)")

        unknown_odd = set(self.odd) - _ALLOWED_ODD_KEYS
        if unknown_odd:
            raise ScenarioValidationError(f"unknown ODD keys: {sorted(unknown_odd)}")
