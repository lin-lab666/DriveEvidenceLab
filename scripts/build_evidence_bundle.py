#!/usr/bin/env python3
"""Build the reproducible evidence bundles published in ``evidence/``.

Two archives are produced:

``evidence/gateE-v2p1-full.tar.gz``
    The complete v2.1 run (protocol v2 on ``builtin/1.1``): per-seed discovery
    reports, per-candidate holdout details, archived episodes, ledger, manifest,
    summary, selection record, audit output.

``evidence/gateE-v1-holdout-summaries.tar.gz``
    Only the v1 holdout ``summary.json`` files, kept so a third party can
    independently recount the "1716/1716 candidates were bit-identical across
    three holdout seeds" claim in the audit report.

Both archives are written **deterministically**: entries are sorted by path and
every entry gets ``mtime=0``, ``uid=gid=0`` and empty owner names, so rebuilding
from identical inputs yields an identical SHA-256. This matters because the
bundle hash is what a reader checks; a non-deterministic tar would make the
publish step unverifiable.

Usage:
    python scripts/build_evidence_bundle.py [--check]

``--check`` rebuilds into a temporary directory and compares the digest with the
existing archive instead of overwriting it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "evidence"

V2_RUN_DIR = REPO_ROOT / "runs" / "formal_experiment_v2p1"
V2_ARCHIVE = EVIDENCE_DIR / "gateE-v2p1-full.tar.gz"

V1_RUN_DIR = REPO_ROOT / "runs" / "formal_experiment_v1"
V1_ARCHIVE = EVIDENCE_DIR / "gateE-v1-holdout-summaries.tar.gz"

# Files that must be present in the v2 bundle. Their absence means the run is
# incomplete, so we fail loudly rather than ship a partial evidence package.
V2_REQUIRED = [
    "summary.json",
    "selection.json",
    "ledger.jsonl",
    "manifest.json",
    "audit.json",
    "report.md",
]


def _iter_files(root: Path, suffixes: Tuple[str, ...] | None = None) -> List[Path]:
    files = [p for p in root.rglob("*") if p.is_file()]
    if suffixes is not None:
        files = [p for p in files if p.suffix in suffixes]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _add_deterministic(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
    data = path.read_bytes()
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.type = tarfile.REGTYPE
    tar.addfile(info, io.BytesIO(data))


def build(archive: Path, top_name: str, files: Iterable[Tuple[Path, str]]) -> str:
    """Write a sorted, mtime-zeroed tar.gz and return its SHA-256 hex digest."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    payload = sorted(files, key=lambda pair: pair[1])
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for path, arcname in payload:
            _add_deterministic(tar, path, f"{top_name}/{arcname}")
    with open(archive, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
            gz.write(raw.getvalue())
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def build_v2(out: Path) -> str:
    missing = [name for name in V2_REQUIRED if not (V2_RUN_DIR / name).exists()]
    if missing:
        raise SystemExit(f"refusing to build: v2 run is missing {missing} in {V2_RUN_DIR}")
    files = [(p, p.relative_to(V2_RUN_DIR).as_posix()) for p in _iter_files(V2_RUN_DIR)]
    return build(out, V2_RUN_DIR.name, files)


def build_v1(out: Path) -> str:
    holdout = V1_RUN_DIR / "holdout"
    if not holdout.exists():
        raise SystemExit(f"refusing to build: {holdout} not found")
    files = [(p, p.relative_to(V1_RUN_DIR).as_posix())
             for p in _iter_files(holdout, suffixes=(".json",))]
    return build(out, V1_RUN_DIR.name, files)


def write_sums(entries: List[Tuple[str, str]]) -> None:
    lines = [f"{digest}  {Path(name).name}" for name, digest in sorted(entries)]
    (EVIDENCE_DIR / "SHA256SUMS").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8", newline="\n")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="rebuild into a temp dir and compare digests instead of overwriting")
    args = ap.parse_args(argv)

    if args.check:
        with tempfile.TemporaryDirectory(prefix="delab_bundle_") as tmp:
            tmpdir = Path(tmp)
            v2 = tmpdir / V2_ARCHIVE.name
            digest = build_v2(v2)
            existing = V2_ARCHIVE
            if not existing.exists():
                print(f"[check] {existing.name} does not exist; run without --check first")
                return 1
            actual = hashlib.sha256(existing.read_bytes()).hexdigest()
            ok = digest == actual
            print(f"[check] rebuilt  {digest}")
            print(f"[check] on disk  {actual}")
            print(f"[check] {'MATCH' if ok else 'MISMATCH'}")
            if not ok:
                print("        the committed bundle does not match a fresh build; "
                      "either the run changed or the archive is stale")
            return 0 if ok else 1

    entries: List[Tuple[str, str]] = []
    v2_digest = build_v2(V2_ARCHIVE)
    entries.append((V2_ARCHIVE.name, v2_digest))
    print(f"built {V2_ARCHIVE.relative_to(REPO_ROOT)}  sha256={v2_digest}")

    if V1_RUN_DIR.exists():
        v1_digest = build_v1(V1_ARCHIVE)
        entries.append((V1_ARCHIVE.name, v1_digest))
        print(f"built {V1_ARCHIVE.relative_to(REPO_ROOT)}  sha256={v1_digest}")
    elif V1_ARCHIVE.exists():
        digest = hashlib.sha256(V1_ARCHIVE.read_bytes()).hexdigest()
        entries.append((V1_ARCHIVE.name, digest))
        print(f"kept  {V1_ARCHIVE.relative_to(REPO_ROOT)}  sha256={digest} (raw v1 run not present)")

    write_sums(entries)
    print(f"wrote {EVIDENCE_DIR / 'SHA256SUMS'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
