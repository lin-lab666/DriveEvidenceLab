#!/usr/bin/env bash
# DriveEvidenceLab — full local verification.
#
# Usage:
#   ./scripts/run_all.sh                  # tests + CLI smoke
#   ./scripts/run_all.sh --with-formal    # also rerun the v2 formal experiment + audit
#   PYTHON=/path/to/python ./scripts/run_all.sh
#
# Everything is executed for real; no step is simulated.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="${PROJECT_ROOT}/src"

WITH_FORMAL=0
for arg in "$@"; do
  case "$arg" in
    --with-formal) WITH_FORMAL=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

echo "=== DriveEvidenceLab run_all.sh ==="
echo "Project root : ${PROJECT_ROOT}"
echo "Python       : $("${PYTHON}" -c 'import sys; print(sys.version.split()[0], sys.executable)')"

cd "${PROJECT_ROOT}"

echo
echo "--- [1/4] unit + integration tests ---"
"${PYTHON}" -m unittest discover -s tests -p "test_*.py"

echo
echo "--- [2/4] CLI smoke: doctor / sample / run / audit / replay / report / search ---"
rm -rf runs/smoke_*
"${PYTHON}" -m driveevidence.cli.main doctor
"${PYTHON}" -m driveevidence.cli.main sample --id smoke --out runs/smoke_scenario.json
"${PYTHON}" -m driveevidence.cli.main run \
    --scenario examples/scenarios/tailgate_risk.json \
    --adapter builtin --seed 123 \
    --run-id smoke_run --out runs
"${PYTHON}" -m driveevidence.cli.main audit --run runs/smoke_run
"${PYTHON}" -m driveevidence.cli.main replay --run runs/smoke_run --seq 1 --adapter builtin
"${PYTHON}" -m driveevidence.cli.main report --run runs/smoke_run --out runs/smoke_run/report.md
"${PYTHON}" -m driveevidence.cli.main search \
    --method random --adapter builtin --budget 16 --seed 2000 \
    --run-id smoke_search --out runs
"${PYTHON}" -m driveevidence.cli.main audit --run runs/smoke_search
"${PYTHON}" -m driveevidence.cli.main report --run runs/smoke_search --format html \
    --out runs/smoke_search/report.html

echo
echo "--- [3/4] evidence bundle verification ---"
if [ -f evidence/SHA256SUMS ]; then
  "${PYTHON}" scripts/verify_evidence_bundle.py

  # The published archives are deterministic; rebuilding must reproduce the
  # exact bytes, otherwise SHA256SUMS is not a meaningful check for a reader.
  if [ -d runs/formal_experiment_v2p1 ]; then
    echo
    echo "--- [3b] evidence bundle determinism (rebuild and compare) ---"
    "${PYTHON}" scripts/build_evidence_bundle.py --check

    echo
    echo "--- [3c] seed coupling audit (D019-C) ---"
    "${PYTHON}" scripts/audit_seed_coupling.py --run runs/formal_experiment_v2p1

    # CommonRoad is an optional dependency; run the interop cross-check only
    # when it is actually installed, and say so explicitly when it is not.
    if "${PYTHON}" -c "import commonroad" >/dev/null 2>&1; then
      echo
      echo "--- [3d] CommonRoad interoperability cross-check (Gate D) ---"
      "${PYTHON}" scripts/verify_commonroad_interop.py --run runs/formal_experiment_v2p1
    else
      echo
      echo "--- [3d] CommonRoad interop skipped (commonroad-io not installed) ---"
    fi
  fi
else
  echo "evidence/ bundle not present; skipping (regenerate with --with-formal)"
fi

if [ "${WITH_FORMAL}" -eq 1 ]; then
  echo
  echo "--- [4/4] protocol v2 formal experiment + independent audit ---"
  # Write to a separate directory so the reference artifacts are never clobbered.
  "${PYTHON}" scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2_rerun
  "${PYTHON}" scripts/audit_scientific_validity.py --v2 runs/formal_experiment_v2_rerun \
      --out runs/formal_experiment_v2_rerun
  "${PYTHON}" scripts/audit_seed_coupling.py --run runs/formal_experiment_v2_rerun
else
  echo
  echo "--- [4/4] formal experiment skipped (pass --with-formal to run it) ---"
  echo "    ~8200 discovery episodes + 384 holdout episodes, roughly 20-60 s on CPU"
fi

echo
echo "=== run_all.sh completed successfully ==="
echo "Evidence packages: ${PROJECT_ROOT}/runs/"
echo "Audit report     : ${PROJECT_ROOT}/docs/SCIENTIFIC_AUDIT.zh-CN.md"
