"""DriveEvidenceLab: Evidence-Driven Autonomous Driving Falsification and Validation Framework.

Simulation-only research toolkit. NOT a safety-certified system;
makes no real-world road safety claims.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    # Single source of truth is the distribution metadata in pyproject.toml.
    __version__ = _pkg_version("driveevidence")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.2.0"

__all__ = ["__version__"]
