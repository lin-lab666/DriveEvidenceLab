"""SHA-256 file manifest for evidence package integrity verification."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ManifestError(RuntimeError):
    """Raised when manifest operations fail."""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(run_dir: str, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a SHA-256 manifest of all files under run_dir (except manifest.json)."""
    exclude = set(exclude or ["manifest.json"])
    run_path = Path(run_dir).resolve()
    files: Dict[str, Dict[str, Any]] = {}
    for p in run_path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(run_path).as_posix()
        if rel in exclude:
            continue
        files[rel] = {"sha256": _sha256_file(str(p)), "size": p.stat().st_size}
    manifest = {
        "generator": "driveevidence/manifest/1.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    manifest_path = run_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    return manifest


def verify_manifest(run_dir: str) -> Dict[str, str]:
    """Verify all files recorded in manifest.json; return status per relative path."""
    run_path = Path(run_dir).resolve()
    manifest_path = run_path / "manifest.json"
    if not manifest_path.exists():
        return {"__manifest__": "missing"}
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    expected = manifest.get("files", {})
    results: Dict[str, str] = {"__manifest__": "ok"}
    for rel, meta in expected.items():
        p = run_path / rel
        if not p.exists():
            results[rel] = "missing"
            continue
        actual = _sha256_file(str(p))
        if actual == meta.get("sha256"):
            results[rel] = "ok"
        else:
            results[rel] = "hash-mismatch"
    return results
