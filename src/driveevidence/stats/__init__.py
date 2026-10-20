"""Statistics: confidence intervals, hypothesis tests, and multiple-testing correction.

Pure-standard-library implementations (``math`` only); no SciPy required.
"""

from driveevidence.stats.estimators import (
    benjamini_hochberg,
    binomial_tail_p,
    bootstrap_p_value,
    cohens_h,
    fisher_exact_two_sided,
    holm_correction,
    newcombe_diff_ci,
    paired_bootstrap_ci,
    stable_failure_yield,
    wilson_ci,
)

__all__ = [
    "wilson_ci",
    "stable_failure_yield",
    "paired_bootstrap_ci",
    "newcombe_diff_ci",
    "fisher_exact_two_sided",
    "cohens_h",
    "holm_correction",
    "benjamini_hochberg",
    "binomial_tail_p",
    "bootstrap_p_value",
]
