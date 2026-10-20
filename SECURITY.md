# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.2.x | ✅ |
| < 0.2 | ❌ |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Until the project has a dedicated security e-mail address (this repository is
pre-public-release), report suspected vulnerabilities by opening a GitHub
issue with the title prefixed `[security]` **containing no technical detail**,
so the maintainers can set up a private channel, or contact the maintainers
through the GitHub profile that publishes the repository.

What counts as a security issue here:

- Any way for untrusted scenario JSON (the `ir/v1` input format) to cause
  code execution, unbounded resource use, or evidence-file tampering that
  **passes** the manifest/ledger verification.
- Path traversal or unsafe extraction when replaying archived episodes.
- Any leak of local absolute paths or credentials through the published
  evidence bundles or the public-release build.

Scope note: this is simulation-only research software. Findings that require
a real vehicle, or that only affect hypothetical integrations, are out of
scope for a fix but still welcome as reports.

## Verification tooling

The repository ships its own integrity tooling, which doubles as an audit
surface:

```bash
python scripts/verify_evidence_bundle.py   # bundle checksums, hash chain, statistics
python scripts/privacy_scan.py --root .    # secret/path/PII scan (content, names, git history)
```
