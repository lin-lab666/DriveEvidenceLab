"""Append-only, hash-chained run ledger for auditability.

Each record links to the previous record's SHA-256 digest. Tampering with
any record invalidates the chain on verification.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


GENESIS_HASH = "GENESIS"


class LedgerError(RuntimeError):
    """Raised when the ledger integrity check fails."""


class RunLedger:
    """Append-only JSONL ledger with per-record SHA-256 hash chaining.

    This class is NOT thread-safe by design; it expects single-process writes.
    """

    EVENT_RUN_STARTED = "run_started"
    EVENT_EPISODE_STARTED = "episode_started"
    EVENT_EPISODE_COMPLETED = "episode_completed"
    EVENT_EPISODE_FAILED = "episode_failed"
    EVENT_EPISODE_INFEASIBLE = "episode_infeasible"
    EVENT_BUDGET_SNAPSHOT = "budget_snapshot"
    EVENT_RUN_FINISHED = "run_finished"

    def __init__(self, run_dir: str, run_id: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.run_dir = os.path.abspath(run_dir)
        self.run_id = run_id
        self.ledger_path = os.path.join(self.run_dir, "ledger.jsonl")
        os.makedirs(self.run_dir, exist_ok=True)

        if not os.path.exists(self.ledger_path):
            self._seq = 0
            self._last_hash = GENESIS_HASH
            self.record(
                self.EVENT_RUN_STARTED,
                {"run_id": run_id, "config": config or {}, "created_at": self._now()},
            )
        else:
            entries = self.entries()
            if entries:
                self._seq = entries[-1]["seq"]
                self._last_hash = entries[-1]["hash"]
            else:
                self._seq = 0
                self._last_hash = GENESIS_HASH

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _canonical(payload: Dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    def _next_hash(self, prev_hash: str, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(
            self._canonical({"prev_hash": prev_hash, "payload": payload})
        ).hexdigest()

    def record(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._seq += 1
        seq = self._seq
        ts = self._now()
        body = {"seq": seq, "ts": ts, "type": event_type, "payload": payload}
        entry_hash = self._next_hash(self._last_hash, body)
        entry = {**body, "prev_hash": self._last_hash, "hash": entry_hash}
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        self._last_hash = entry_hash
        return entry

    def entries(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.ledger_path):
            return []
        out = []
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Return (ok, first_bad_seq). first_bad_seq is None if chain is intact."""
        prev_hash = GENESIS_HASH
        for entry in self.entries():
            expected = hashlib.sha256(
                self._canonical({"prev_hash": prev_hash, "payload": {
                    "seq": entry["seq"], "ts": entry["ts"],
                    "type": entry["type"], "payload": entry["payload"],
                }})
            ).hexdigest()
            if entry["prev_hash"] != prev_hash or entry["hash"] != expected:
                return False, entry["seq"]
            prev_hash = entry["hash"]
        return True, None

    @classmethod
    def load(cls, run_dir: str) -> "RunLedger":
        ledger_path = os.path.join(run_dir, "ledger.jsonl")
        if not os.path.exists(ledger_path):
            raise LedgerError(f"ledger not found at {ledger_path}")
        entries = []
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        if not entries:
            raise LedgerError("ledger is empty")
        first = entries[0]
        run_id = first["payload"].get("run_id", "unknown")
        config = first["payload"].get("config", {})
        instance = cls.__new__(cls)
        instance.run_dir = os.path.abspath(run_dir)
        instance.run_id = run_id
        instance.ledger_path = ledger_path
        instance._seq = entries[-1]["seq"]
        instance._last_hash = entries[-1]["hash"]
        return instance
