---
name: Bug report
about: Report a defect in the code, tests, or documentation
title: "[Bug] "
labels: bug
assignees: []
---

**Describe the bug**
A clear, concise description of what is wrong.

**To reproduce**
Minimal steps or a short script. Please prefer the public SDK/CLI API over
internal functions where possible.

```python
# minimal reproduction
```

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened — include the full traceback or error message.

**Environment**
- OS (e.g. Windows 11 / Ubuntu 22.04):
- Python version (`python --version`):
- Package version (`python -c "import driveevidence; print(driveevidence.__version__)"`):
- Simulator backend (`builtin` / `highwayenv` / `commonroad`):

**Severity**
- [ ] Critical (crashes, wrong results, data loss)
- [ ] Major (feature broken)
- [ ] Minor (cosmetic / edge case)

**Additional context**
Add any other context. If this concerns a scientific result, please state which
protocol version and evidence artifact it affects.
