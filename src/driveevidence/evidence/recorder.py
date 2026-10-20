"""Driving evidence chain recorder.

Migrated from the original src/evidence/recorder.py prototype (24/24 tests
passed) into the driveevidence package. API preserved.
"""
from __future__ import annotations

import json
from typing import Any, Self

__all__ = ["DrivingEvidenceRecorder"]


class DrivingEvidenceRecorder:
    """Recorder for ego trajectory, discrete events and causal links."""

    def __init__(self, scenario_id: str, sampling_hz: float = 10.0) -> None:
        self._scenario_id: str = scenario_id
        self._sampling_hz: float = sampling_hz
        self._states: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._causal_links: list[dict[str, Any]] = []
        self._next_state_seq: int = 1
        self._next_event_id: int = 1

    @property
    def scenario_id(self) -> str:
        return self._scenario_id

    @property
    def sampling_hz(self) -> float:
        return self._sampling_hz

    def add_state(
        self,
        timestamp: float,
        ego_x: float,
        ego_y: float,
        ego_v: float,
        ego_heading: float,
        **extra: Any,
    ) -> int:
        state: dict[str, Any] = {
            "seq": self._next_state_seq,
            "timestamp": timestamp,
            "ego_x": ego_x,
            "ego_y": ego_y,
            "ego_v": ego_v,
            "ego_heading": ego_heading,
        }
        state.update(extra)
        self._states.append(state)
        self._next_state_seq += 1
        return state["seq"]

    def add_event(
        self,
        timestamp: float,
        event_type: str,
        description: str = "",
        severity: int = 1,
    ) -> int:
        event: dict[str, Any] = {
            "id": self._next_event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "description": description,
            "severity": severity,
        }
        self._events.append(event)
        self._next_event_id += 1
        return event["id"]

    def link_cause(
        self,
        effect_event_id: int,
        cause_event_id: int,
        relation: str,
        confidence: float,
    ) -> None:
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be within [0.0, 1.0], got {confidence!r}"
            )
        known_ids = {event["id"] for event in self._events}
        for event_id in (effect_event_id, cause_event_id):
            if event_id not in known_ids:
                raise KeyError(f"unknown event id: {event_id}")
        self._causal_links.append(
            {
                "effect_event_id": effect_event_id,
                "cause_event_id": cause_event_id,
                "relation": relation,
                "confidence": confidence,
            }
        )

    def to_json(self, path: str) -> None:
        payload: dict[str, Any] = {
            "scenario_id": self._scenario_id,
            "sampling_hz": self._sampling_hz,
            "states": self._states,
            "events": self._events,
            "causal_links": self._causal_links,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: str) -> Self:
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        recorder = cls(
            scenario_id=data["scenario_id"],
            sampling_hz=data["sampling_hz"],
        )
        recorder._states = list(data.get("states", []))
        recorder._events = list(data.get("events", []))
        recorder._causal_links = list(data.get("causal_links", []))
        recorder._next_state_seq = len(recorder._states) + 1
        recorder._next_event_id = len(recorder._events) + 1
        return recorder

    def summary(self) -> dict[str, Any]:
        return {
            "scenario_id": self._scenario_id,
            "n_states": len(self._states),
            "n_events": len(self._events),
            "n_causal_links": len(self._causal_links),
        }
