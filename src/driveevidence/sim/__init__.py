from driveevidence.sim.base import (SimulatorAdapter, EpisodeResult, TrajectorySample, FailureCategory, register_adapter, create_adapter, list_adapters)

# Trigger adapter registration side-effects when driveevidence.sim is imported.
from driveevidence.sim import builtin  # noqa: F401
from driveevidence.sim import highwayenv_adapter  # noqa: F401

# The CommonRoad backend registers unconditionally but imports commonroad-io
# lazily, so the adapter stays listed (and obviously unavailable) instead of
# silently disappearing when the optional dependency is missing.
from driveevidence.sim import commonroad_adapter  # noqa: F401
