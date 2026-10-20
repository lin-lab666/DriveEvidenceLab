## Description

A concise summary of the change and why it is needed.

Fixes # (issue number, if any).

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Test only
- [ ] Refactor (no behaviour change)

## Checklist

- [ ] I ran `python -m unittest discover -s tests -p "test_*.py"` and it passes
      (state the count, e.g. `Ran 141 tests in ... OK`).
- [ ] New code is covered by tests.
- [ ] I did not weaken or delete existing tests or assertions.
- [ ] I updated `CHANGELOG.md`, `docs/PROGRESS.md`, and `docs/DECISIONS.md`
      where the change affects behaviour or published results.
- [ ] If the change touches a frozen protocol, a scientific result, or the
      evidence bundles, I did **not** retroactively rewrite them; I described
      the change and its impact instead.
- [ ] I did not claim multi-agent review, inter-simulator equivalence, or
      external reproduction unless actually performed.

## Scientific integrity note

DriveEvidenceLab treats simulation results as research artefacts, not
real-world safety evidence. If this PR changes any reported number, state
clearly which protocol version and evidence artifact it affects, and whether a
result was withdrawn, corrected, or added.

## Screenshots / evidence (if applicable)

Paste command output, test results, or links to artifacts.
