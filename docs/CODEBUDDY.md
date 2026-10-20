# DriveEvidenceLab project instructions for AI development agents

This repository is a simulation-only autonomous-driving research toolkit, NOT a safety-certified system. Do not make real-world road safety claims, operate vehicles, or publish control instructions for physical deployment.

- Never edit existing CornerCaseLab private/public archives or SafeFlipLab experiment archives.
- Every claimed result must be traceable to actual raw simulation records and their hashes; mocks are only for tests.
- Formal datasets, protocol and seeds must be frozen before confirmatory evaluation; do not retroactively rewrite them.
- Record every launched episode including error, cancelled, crashed, and timeout runs; every retry is counted.
- Stage all new work under the dedicated project workspace. Do not change global Windows ACLs/security settings, disable Kaspersky, or leak secrets.
- Never claim multi-agent teamwork without evidence of distinct actual sessions/tasks.
- Never claim inter-simulator equivalence without checking semantics, units, frame conventions, scenario capability and unsupported features.
- All code modules require tests, independent review, dependency/license checks and examples.
- Do not push to public GitHub without explicit confirmation of the exact release and public visibility.
- Prefer honest partial implementation or negative results over fake completeness or fabricated metrics.
- Maintain `docs/PROGRESS.md` and `docs/DECISIONS.md`; update on every gate.

See START_HERE_WorkBuddy.md, SPEC.md, RESEARCH_PROTOCOL.md and ACCEPTANCE_AND_RELEASE.md for the full plan.
