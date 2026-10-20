#!/usr/bin/env python
"""Privacy scan for a repository that is about to become public.

Checks three surfaces separately, because they fail differently:

  1. working tree file contents   -> what a visitor reads on the landing page
  2. file / directory names       -> what shows up in the file browser
  3. git history                  -> what ``git log -p`` reveals even after a
                                     file has been cleaned up in a later commit

Patterns cover: absolute Windows/macOS/Linux home paths (local account name),
cloud/API credentials, private key blocks, and non-placeholder e-mail
addresses.  Findings are reported per file with line numbers; the exit code is
non-zero when any hard violation is found.

Usage:
    python scripts/privacy_scan.py --root . --git
    python scripts/privacy_scan.py --root ../DriveEvidenceLab-public --git --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# --------------------------------------------------------------------------
# patterns
# --------------------------------------------------------------------------
# Captures the account segment of an absolute home path.  The project path
# itself (D:/DriveEvidenceLab) is not personal data; a Windows account name is.
PATTERNS = {
    "windows-home-path": re.compile(
        r"[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"'`<>|]+)", re.IGNORECASE
    ),
    # Negative lookbehind so that "C:/Users/x" is not also reported as a macOS
    # home path (the Windows pattern already covers it).
    "macos-home-path": re.compile(r"(?<![A-Za-z]:)/Users/([^/\s\"'`<>|]+)"),
    "linux-home-path": re.compile(r"(?<![A-Za-z]:)/home/([^/\s\"'`<>|]+)"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}

# Home-path account names that are generic documentation placeholders rather
# than a real person's account.
PLACEHOLDER_ACCOUNTS = {
    "user",
    "username",
    "name",
    "you",
    "yourname",
    "me",
    "example",
    "<user>",
    "${USER}",
    "$USER",
    "%USERNAME%",
    "...",
    "…",
    "*",
    "x",
    "runner",
    "ubuntu",
    "root",
}

# E-mail addresses that are explicitly non-deliverable / illustrative.
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "invalid", "localhost"}
ALLOWED_EMAIL_LOCALS = {"noreply", "no-reply", "team", "you", "user", "your"}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".gz", ".zip", ".whl", ".tar", ".tgz", ".pyc", ".so", ".dll", ".exe",
}

# The scanner necessarily contains the patterns it looks for; scanning itself
# only produces self-matches.
SELF_PATH = "scripts/privacy_scan.py"

SKIP_DIRS = {
    ".git", "build", "dist", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "htmlcov", ".venv", "venv", "node_modules",
}

# Errors that are expected to be clean; kept as an allowlist so the report is
# explicit rather than silently filtered.
CONTENT_ALLOWLIST = {
    "team@driveevidencelab.invalid": "project commit identity, non-deliverable domain",
}


@dataclass
class Finding:
    surface: str
    path: str
    line: Optional[int]
    pattern: str
    excerpt: str

    def as_dict(self) -> dict:
        return {
            "surface": self.surface,
            "path": self.path,
            "line": self.line,
            "pattern": self.pattern,
            "excerpt": self.excerpt,
        }


@dataclass
class Report:
    root: str
    scanned_files: int = 0
    findings: List[Finding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def hard(self) -> List[Finding]:
        return self.findings

    def ok(self) -> bool:
        return not self.findings


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if rel.as_posix() == SELF_PATH:
            continue
        yield path


def _is_placeholder_account(account: str) -> bool:
    a = account.strip().lower()
    if a in PLACEHOLDER_ACCOUNTS:
        return True
    # A "account" containing regex metacharacters is a fragment of a pattern
    # definition (e.g. the scanner's own source), not a real account name.
    if any(ch in "[]()\\|*+?{}^$" for ch in a):
        return True
    return False


def _is_allowed_email(addr: str) -> bool:
    local, _, domain = addr.partition("@")
    if domain.lower() in ALLOWED_EMAIL_DOMAINS:
        return True
    if local.lower() in ALLOWED_EMAIL_LOCALS:
        return True
    return False


def scan_text(
    surface: str, label: str, text: str, report: Report, line_offset: bool = True
) -> None:
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            excerpt = match.group(0)
            if name in ("windows-home-path", "macos-home-path", "linux-home-path"):
                account = match.group(1)
                if _is_placeholder_account(account):
                    continue
                excerpt = f"<home of account {account!r}>"
            elif name == "email":
                if _is_allowed_email(excerpt):
                    continue
                if excerpt in CONTENT_ALLOWLIST:
                    continue
            line_no = None
            if line_offset:
                line_no = text.count("\n", 0, match.start()) + 1
            report.findings.append(
                Finding(
                    surface=surface,
                    path=label,
                    line=line_no,
                    pattern=name,
                    excerpt=excerpt[:120],
                )
            )


def scan_tree(root: Path, report: Report) -> None:
    for path in _iter_files(root):
        report.scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            report.notes.append(f"skipped (undecodable): {path.relative_to(root)}")
            continue
        scan_text("content", str(path.relative_to(root)), text, report)


def scan_names(root: Path, report: Report) -> None:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        for part in rel.parts:
            lowered = part.lower()
            # Only flag a path component that matches a real account name, not
            # arbitrary substrings such as a 5-digit number inside a hash.
            if re.fullmatch(r"[0-9]{4,6}", part):
                report.findings.append(
                    Finding(
                        surface="path",
                        path=str(rel),
                        line=None,
                        pattern="numeric-user-directory",
                        excerpt=part,
                    )
                )
            elif lowered.endswith((".env", ".pem", ".key")) or lowered in {
                "id_rsa",
                "id_ed25519",
                ".netrc",
                ".npmrc",
                ".pypirc",
            }:
                report.findings.append(
                    Finding(
                        surface="path",
                        path=str(rel),
                        line=None,
                        pattern="sensitive-filename",
                        excerpt=part,
                    )
                )


def scan_archives(root: Path, report: Report, max_member_bytes: int = 8 << 20) -> None:
    """Scan inside .tar.gz / .tgz / .zip archives.

    Binary archives are otherwise skipped by the content scan, which is a real
    blind spot: the evidence bundles *are* the published artifacts.  Member
    names are checked too, since a path can leak in a directory entry.
    """
    import tarfile
    import zipfile

    text_suffixes = {
        ".json", ".jsonl", ".md", ".txt", ".py", ".csv", ".yml", ".yaml",
        ".toml", ".cfg", ".ini", ".log",
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        lowered = path.name.lower()
        try:
            if lowered.endswith((".tar.gz", ".tgz")):
                with tarfile.open(path, mode="r:gz") as tf:
                    for member in tf.getmembers():
                        scan_text(
                            "archive-name",
                            f"{rel.as_posix()}!{member.name}",
                            member.name,
                            report,
                            line_offset=False,
                        )
                        if not member.isfile() or member.size > max_member_bytes:
                            continue
                        if Path(member.name).suffix.lower() not in text_suffixes:
                            continue
                        fh = tf.extractfile(member)
                        if fh is None:
                            continue
                        try:
                            text = fh.read().decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                        scan_text(
                            "archive-content",
                            f"{rel.as_posix()}!{member.name}",
                            text,
                            report,
                            line_offset=False,
                        )
            elif lowered.endswith(".zip"):
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        scan_text(
                            "archive-name",
                            f"{rel.as_posix()}!{info.filename}",
                            info.filename,
                            report,
                            line_offset=False,
                        )
                        if info.file_size > max_member_bytes:
                            continue
                        if Path(info.filename).suffix.lower() not in text_suffixes:
                            continue
                        try:
                            text = zf.read(info).decode("utf-8")
                        except (UnicodeDecodeError, RuntimeError):
                            continue
                        scan_text(
                            "archive-content",
                            f"{rel.as_posix()}!{info.filename}",
                            text,
                            report,
                            line_offset=False,
                        )
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
            report.notes.append(f"archive unreadable: {rel.as_posix()} ({exc})")


def scan_git_history(root: Path, report: Report) -> None:
    """Scan every blob reachable from HEAD, plus commit author/committer fields."""
    try:
        has_git = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root,
            capture_output=True,
            text=True,
        ).returncode == 0
    except FileNotFoundError:
        report.notes.append("git not available; history scan skipped")
        return
    if not has_git:
        report.notes.append("no git repository at root; history scan skipped")
        return

    revs = subprocess.run(
        ["git", "rev-list", "--all"], cwd=root, capture_output=True, text=True
    )
    commits = revs.stdout.split()
    report.notes.append(f"git history: {len(commits)} commits scanned")

    ids = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    # rev-list --objects gives "<oid> <path>".  Keeping the path lets us apply
    # the same exclusions as the working-tree scan — otherwise the scanner's own
    # pattern definitions show up as "leaked home paths".
    oid_paths = []
    for line in ids:
        if not line.strip():
            continue
        oid, _, path = line.partition(" ")
        if path:
            rel_parts = Path(path).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            if Path(path).as_posix() == SELF_PATH:
                continue
        oid_paths.append((oid, path))

    blob_ids = [oid for oid, _ in oid_paths]

    # Batch cat-file for speed.
    proc = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        cwd=root,
        input="\n".join(blob_ids),
        capture_output=True,
        text=True,
    )
    blob_type = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            blob_type[parts[0]] = parts[1]

    for oid, path in oid_paths:
        if blob_type.get(oid) != "blob":
            continue
        content = subprocess.run(
            ["git", "cat-file", "-p", oid], cwd=root, capture_output=True
        ).stdout
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        label = f"{path or 'blob'}@{oid[:8]}" if path else f"blob:{oid[:12]}"
        scan_text("history-blob", label, text, report, line_offset=False)

    meta = subprocess.run(
        ["git", "log", "--all", "--format=%an|%ae|%cn|%ce"],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout
    for line in sorted(set(meta.splitlines())):
        if not line.strip():
            continue
        scan_text("history-meta", "commit-identity", line, report, line_offset=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="repository root to scan")
    ap.add_argument("--git", action="store_true", help="also scan git history blobs")
    ap.add_argument(
        "--no-archives", action="store_true", help="skip .tar.gz/.zip member scanning"
    )
    ap.add_argument("--json", default=None, help="write machine-readable report here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    report = Report(root=str(root))

    scan_tree(root, report)
    scan_names(root, report)
    if not args.no_archives:
        scan_archives(root, report)
    if args.git:
        scan_git_history(root, report)

    by_surface: Dict[str, List[Finding]] = {}
    for f in report.findings:
        by_surface.setdefault(f.surface, []).append(f)

    if not args.quiet:
        print(f"privacy scan: {root}")
        print(f"  files scanned : {report.scanned_files}")
        print(f"  findings      : {len(report.findings)}")
        for surface in ("content", "path", "history-blob", "history-meta"):
            items = by_surface.get(surface, [])
            print(f"  - {surface:12s}: {len(items)}")
        for note in report.notes:
            print(f"  note: {note}")
        if report.findings:
            print()
            for f in report.findings[:200]:
                loc = f"{f.path}:{f.line}" if f.line else f.path
                print(f"  [{f.surface}] {loc}  {f.pattern}  -> {f.excerpt}")
            if len(report.findings) > 200:
                print(f"  ... and {len(report.findings) - 200} more")
        print()
        print("RESULT:", "CLEAN" if report.ok() else "VIOLATIONS FOUND")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "root": report.root,
                    "scanned_files": report.scanned_files,
                    "notes": report.notes,
                    "findings": [f.as_dict() for f in report.findings],
                    "clean": report.ok(),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    return 0 if report.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
