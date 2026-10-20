#!/usr/bin/env python
"""Build a privacy-scrubbed public release copy of the research repository.

Design constraints (deliberate):

* The **private research repository is never modified.**  Its git history is
  the audit anchor for the frozen protocol and the archived evidence bundles,
  so rewriting it would invalidate every hash recorded in the reports.
* The public copy is built from ``git ls-files`` of the private repo, which
  already excludes ``runs/`` (raw, ~71 MB) and ``.workbuddy/`` (local agent
  state).  Nothing untracked is copied, so a stray file cannot leak.
* Only *identity* data is redacted: absolute home paths (local Windows account
  name).  Scientific content, commit messages and numbers are untouched.
* The public repository gets a **single curated commit**, and the release notes
  state that explicitly.  It is not presented as the original development
  history.
* Redactions are logged file-by-file in ``PUBLIC_RELEASE.md`` so a reader can
  see exactly what was changed and why.

Usage:
    python scripts/build_public_release.py --out ../DriveEvidenceLab-public
    python scripts/build_public_release.py --out ../DriveEvidenceLab-public --commit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Anything matching these is refused even if it somehow became tracked.
HARD_EXCLUDE_DIRS = {".workbuddy", "runs", ".git", "__pycache__", "build", "dist"}
HARD_EXCLUDE_SUFFIXES = {".key", ".pem", ".env"}

# Tooling that must contain the detection patterns verbatim to work.  Redacting
# these would corrupt the scanners themselves; they contain no real paths.
NO_REDACT = {
    "scripts/privacy_scan.py",
    "scripts/build_public_release.py",
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".gz", ".zip", ".whl", ".tar", ".tgz", ".pyc", ".so", ".dll", ".exe",
}

# Ordered redaction rules.  Each entry is (name, compiled regex, replacement).
# Only the home-directory segment is replaced; everything after it stays, so
# the document still reads correctly.
REDACTIONS: List[Tuple[str, re.Pattern, str]] = [
    (
        "home-path",
        re.compile(
            r"(?:[A-Za-z]:[\\/]+Users[\\/]+|[A-Za-z]:[\\/]+Documents and Settings[\\/]+)"
            r"(?!user\b|username\b|you\b|name\b|\.\.\.|…)([^\\/\s\"'`<>|]+)",
            re.IGNORECASE,
        ),
        "<LOCAL_HOME>",
    ),
    (
        "unix-home-path",
        re.compile(r"(?<![A-Za-z]:)/(?:Users|home)/(?!user\b|username\b|you\b)([^/\s\"'`<>|]+)"),
        "<LOCAL_HOME>",
    ),
]


def run(cmd: List[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)


def tracked_files(root: Path) -> List[str]:
    res = run(["git", "ls-files"], cwd=root)
    if res.returncode != 0:
        raise SystemExit(f"not a git repository: {root}\n{res.stderr}")
    return [line for line in res.stdout.splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_binary(path: Path) -> bool:
    return path.suffix.lower() in BINARY_SUFFIXES


def redact_text(text: str) -> Tuple[str, Dict[str, int]]:
    counts: Dict[str, int] = {}
    for name, pattern, repl in REDACTIONS:
        new_text, n = pattern.subn(repl, text)
        if n:
            counts[name] = counts.get(name, 0) + n
            text = new_text
    return text, counts


def git_identity(root: Path) -> Tuple[str, str, str]:
    """Return (author name, author email, HEAD commit date as ISO-8601)."""
    name = run(["git", "config", "user.name"], cwd=root).stdout.strip() or "DriveEvidenceLab Team"
    email = (
        run(["git", "config", "user.email"], cwd=root).stdout.strip()
        or "team@driveevidencelab.invalid"
    )
    date = run(["git", "log", "-1", "--format=%cI"], cwd=root).stdout.strip()
    return name, email, date


def protocol_fingerprints(root: Path) -> Dict[str, object]:
    """Collect the freeze hashes that must survive into the public copy."""
    out: Dict[str, object] = {}
    freeze = root / "docs" / "PROTOCOL-v2.freeze.json"
    if freeze.exists():
        out["protocol_v2_freeze"] = json.loads(freeze.read_text(encoding="utf-8"))
    sums = root / "evidence" / "SHA256SUMS"
    if sums.exists():
        out["evidence_sha256sums_sha256"] = sha256_file(sums)
        out["evidence_sha256sums_lines"] = len(
            [ln for ln in sums.read_text(encoding="utf-8").splitlines() if ln.strip()]
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="target directory for the public copy")
    ap.add_argument("--commit", action="store_true", help="initialise git and make one commit")
    ap.add_argument("--tag", default="v0.2.0-research-preview", help="tag name if --commit")
    ap.add_argument("--force", action="store_true", help="replace an existing --out directory")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            print(f"error: {out} already exists (use --force to replace)", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    out.mkdir(parents=True)

    files = tracked_files(REPO_ROOT)
    copied: List[str] = []
    redacted: Dict[str, Dict[str, int]] = {}
    excluded: List[str] = []

    for rel in files:
        src = REPO_ROOT / rel
        parts = Path(rel).parts
        if any(p in HARD_EXCLUDE_DIRS for p in parts) or src.suffix.lower() in HARD_EXCLUDE_SUFFIXES:
            excluded.append(rel)
            continue
        if not src.exists():
            excluded.append(f"{rel} (missing on disk)")
            continue

        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if is_binary(src):
            shutil.copy2(src, dst)
            copied.append(rel)
            continue

        text = src.read_text(encoding="utf-8")
        if rel in NO_REDACT:
            # Copy verbatim; these files legitimately contain the patterns.
            dst.write_text(text, encoding="utf-8", newline="\n")
            copied.append(rel)
            continue
        new_text, counts = redact_text(text)
        dst.write_text(new_text, encoding="utf-8", newline="\n")
        copied.append(rel)
        if counts:
            redacted[rel] = counts

    fingerprints = protocol_fingerprints(REPO_ROOT)
    head = run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.strip()

    # Placeholders in packaging metadata must never reach a public repository.
    blockers: List[str] = []
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists() and "PLACEHOLDER" in pyproject.read_text(encoding="utf-8"):
        blockers.append(
            "`pyproject.toml` still contains a `PLACEHOLDER` repository URL; "
            "set the real URL before publishing."
        )

    manifest = {
        "source_repository": "private research repository (not published)",
        "source_head_commit": head,
        "file_count": len(copied),
        "files": {rel: sha256_file(out / rel) for rel in copied},
    }
    (out / "PUBLIC_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    notes = render_release_notes(head, copied, redacted, excluded, fingerprints, blockers)
    (out / "PUBLIC_RELEASE.md").write_text(notes, encoding="utf-8", newline="\n")

    if blockers:
        print("BLOCKERS:")
        for item in blockers:
            print(f"  - {item}")
    print(f"public copy : {out}")
    print(f"files       : {len(copied)}")
    print(f"redacted    : {len(redacted)} file(s)")
    for rel, counts in sorted(redacted.items()):
        print(f"  - {rel}: {counts}")
    if excluded:
        print(f"excluded    : {excluded}")

    if args.commit:
        # A --commit is the actual publication step. If packaging metadata still
        # contains a PLACEHOLDER URL, refuse to produce a publishable copy: a
        # placeholder must never reach a public repository.
        if blockers:
            print("error: refusing to commit a public copy with outstanding blockers:", file=sys.stderr)
            for item in blockers:
                print(f"  - {item}", file=sys.stderr)
            return 1
        init_public_git(out, head, args.tag)

    return 0


def render_release_notes(
    head: str,
    copied: List[str],
    redacted: Dict[str, Dict[str, int]],
    excluded: List[str],
    fingerprints: Dict[str, object],
    blockers: List[str],
) -> str:
    """Render PUBLIC_RELEASE.md. Blocks are joined with blank lines so the
    Markdown renders correctly without hand-counting newlines."""
    blocks: List[str] = []

    blocks.append(
        "# Public release provenance\n\n"
        "This directory is a **privacy-scrubbed public copy** of a private research\n"
        "repository. It is not the original development history."
    )

    blocks.append(
        "\n".join(
            [
                "## What this copy is",
                f"- Built from `git ls-files` of the private repository at commit `{head}`.",
                "- Contains **one curated commit**. The private repository keeps the full",
                "  incremental history; that history is not published because it contains",
                "  local absolute paths.",
                f"- {len(copied)} files were copied. Every file's SHA-256 is recorded in",
                "  `PUBLIC_MANIFEST.json`.",
            ]
        )
    )

    removed: List[str] = ["## What was removed or changed"]
    if redacted:
        removed.append(
            "Only *identity* data was redacted: the absolute home path of the machine\n"
            "that produced the artifacts (it contained the local Windows account name).\n"
            "No scientific content, number, commit message or result was altered."
        )
        table = ["| File | Redactions |", "|---|---|"]
        for rel, counts in sorted(redacted.items()):
            detail = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items()))
            table.append(f"| `{rel}` | {detail} |")
        removed.append("\n".join(table))
        removed.append(
            "The redaction token is `<LOCAL_HOME>`. Each replaced string was an\n"
            "absolute interpreter path; the surrounding sentence is unchanged, so the\n"
            "record's meaning is preserved."
        )
    else:
        removed.append("No file required redaction.")
    if excluded:
        removed.append(
            "Hard-excluded paths:\n\n" + "\n".join(f"- `{r}`" for r in excluded)
        )
    removed.append(
        "`runs/` (raw per-episode artifacts, ~71 MB) and `.workbuddy/` (local agent\n"
        "state) are not published. The raw formal-experiment artifacts are instead\n"
        "distributed as the archived bundles under `evidence/`, which are the exact\n"
        "inputs the audit scripts verify."
    )
    blocks.append("\n\n".join(removed))

    blocker_block: List[str] = ["## Outstanding blockers before publication"]
    if blockers:
        blocker_block.append("Detected automatically at build time; the build does not fix them.")
        blocker_block.append("\n".join(f"- {item}" for item in blockers))
    else:
        blocker_block.append("None detected at build time.")
    blocks.append("\n\n".join(blocker_block))

    blocks.append(
        "## Freeze fingerprints that survive the scrubbing\n\n"
        "These values let a third party verify the protocol and the evidence archive\n"
        "without access to the private git history:\n\n"
        "```json\n"
        + json.dumps(fingerprints, indent=2, sort_keys=True)
        + "\n```"
    )

    blocks.append(
        "### Verification\n\n"
        "```bash\n"
        "python scripts/verify_evidence_bundle.py        # checksums -> hash chain -> manifest -> recompute\n"
        "python scripts/audit_independent_recompute.py   # statistics from scratch, no project imports\n"
        "```\n\n"
        "The independent recompute script needs the extracted run directory; see\n"
        "`evidence/README.md` for how the bundles map onto `runs/` paths."
    )

    blocks.append(
        "## What this copy does NOT establish\n\n"
        "- It does not establish external (third-party) reproduction. All experiments\n"
        "  were produced by one author on one machine, so conclusion layer **T3**\n"
        "  remains unmet.\n"
        "- It does not establish cross-simulator dynamics validation. Gate D is\n"
        "  **PARTIAL**: CommonRoad scenario exchange was verified with the real\n"
        "  `commonroad-io` library, but no third-party dynamics engine was integrated.\n"
        "- Results are specific to the `builtin` kinematic simulator, the `safe_follow`\n"
        "  planner and a single-lead-vehicle straight-road scenario family."
    )

    return "\n\n".join(blocks).rstrip() + "\n"


def init_public_git(out: Path, source_head: str, tag: str) -> None:
    name, email, date = git_identity(REPO_ROOT)
    run(["git", "init", "-b", "main"], cwd=out)
    run(["git", "config", "user.name", name], cwd=out)
    run(["git", "config", "user.email", email], cwd=out)
    run(["git", "add", "-A"], cwd=out)
    message = (
        "release: DriveEvidenceLab v0.2.0 research preview (public copy)\n\n"
        "Privacy-scrubbed public snapshot of the private research repository.\n"
        f"Source commit: {source_head}\n\n"
        "This is a single curated commit, not the incremental development history.\n"
        "Local absolute paths were replaced with <LOCAL_HOME>; no scientific\n"
        "content, result or commit message was altered. See PUBLIC_RELEASE.md.\n"
    )
    env = {
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
    res = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=out,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, **env},
    )
    if res.returncode != 0:
        print(f"error: git commit failed\n{res.stderr}", file=sys.stderr)
        raise SystemExit(1)
    run(["git", "tag", "-a", tag, "-m", f"DriveEvidenceLab {tag}"], cwd=out)
    print(f"git          : initialised with one commit, tag {tag}")


if __name__ == "__main__":
    sys.exit(main())
