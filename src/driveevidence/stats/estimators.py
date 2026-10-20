"""Statistical estimators for falsification yields and comparisons.

All routines are pure functions. They do NOT make real-world safety claims.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np


def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for binomial proportion.

    Wilson, E. B. (1927). Probable inference, the law of succession,
    and statistical inference. JASA, 22(158), 209-212.
    """
    if n <= 0:
        return 0.0, 1.0
    if k < 0 or k > n:
        raise ValueError(f"k={k} out of range [0, n={n}]")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    width = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n) / denom
    lo = max(0.0, centre - width)
    hi = min(1.0, centre + width)
    # Guard against floating-point rounding at the boundary.
    if hi >= 1.0 - 1e-15:
        hi = 1.0
    if lo <= 1e-15:
        lo = 0.0
    return lo, hi


def stable_failure_yield(
    confirmed: int, nominated: int, z: float = 1.96
) -> Tuple[float, Tuple[float, float, float]]:
    """Yield point estimate + Wilson CI for stable failure yield.

    Returns (yield, (lo, centre, hi)).
    """
    if nominated <= 0:
        return 0.0, (0.0, 0.0, 1.0)
    point = confirmed / nominated
    lo, hi = wilson_ci(confirmed, nominated, z)
    return point, (lo, point, hi)


def paired_bootstrap_ci(
    diffs: List[float], n_boot: int = 2000, seed: int = 0, alpha: float = 0.05
) -> Tuple[float, float]:
    """Percentile bootstrap CI for mean of paired differences.

    Efron, B. (1979). Bootstrap methods: another look at the jackknife.
    Annals of Statistics, 7(1), 1-26.
    """
    if not diffs:
        return 0.0, 0.0
    rng = np.random.default_rng(seed)
    arr = np.asarray(diffs, dtype=float)
    boot_means = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        boot_means.append(float(np.mean(sample)))
    boot_means = np.asarray(boot_means)
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return lo, hi


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for two proportions.

    Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences.
    """
    if not (0 <= p1 <= 1) or not (0 <= p2 <= 1):
        raise ValueError("proportions must be in [0, 1]")
    return 2 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))


def holm_correction(pvals: List[float]) -> List[float]:
    """Holm-Bonferroni step-down adjusted p-values."""
    m = len(pvals)
    if m == 0:
        return []
    indexed = sorted(enumerate(pvals), key=lambda x: x[1])
    adjusted = [0.0] * m
    prev = 0.0
    for rank, (idx, p) in enumerate(indexed, start=1):
        adj = min(1.0, p * (m - rank + 1))
        adj = max(adj, prev)
        adjusted[idx] = adj
        prev = adj
    return adjusted


def benjamini_hochberg(pvals: List[float]) -> List[float]:
    """Benjamini-Hochberg FDR adjusted p-values."""
    m = len(pvals)
    if m == 0:
        return []
    indexed = sorted(enumerate(pvals), key=lambda x: x[1])
    adjusted = [0.0] * m
    running_min = 1.0
    for rank, (idx, p) in enumerate(indexed, start=1):
        adj = min(1.0, p * m / rank)
        running_min = min(running_min, adj)
        adjusted[idx] = running_min
    return adjusted


def newcombe_diff_ci(
    k1: int, n1: int, k2: int, n2: int, z: float = 1.96
) -> Tuple[float, float, float]:
    """Newcombe hybrid-score CI for the difference ``p2 - p1``.

    Newcombe, R. G. (1998). Interval estimation for the difference between
    independent proportions: comparison of eleven methods. Statistics in
    Medicine, 17(8), 873-890. Method 10 (hybrid score).

    Returns ``(diff, lo, hi)`` where ``diff = k2/n2 - k1/n1``.
    Degenerate inputs (``n1 == 0`` or ``n2 == 0``) return ``(0.0, -1.0, 1.0)``
    and are flagged by the caller, not silently treated as evidence.
    """
    if n1 <= 0 or n2 <= 0:
        return 0.0, -1.0, 1.0
    p1 = k1 / n1
    p2 = k2 / n2
    l1, u1 = wilson_ci(k1, n1, z)
    l2, u2 = wilson_ci(k2, n2, z)
    diff = p2 - p1
    lo = diff - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    hi = diff + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    return diff, max(-1.0, lo), min(1.0, hi)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test p-value for table ``[[a, b], [c, d]]``.

    Uses the hypergeometric distribution directly (no SciPy dependency).
    Row 1 = method 2 successes/failures, row 2 = method 1 successes/failures.
    The two-sided p-value sums probabilities of tables whose probability is no
    greater than the observed table's, which is the standard convention.

    Returns 1.0 for degenerate tables where no test is defined.
    """
    for v in (a, b, c, d):
        if v < 0:
            raise ValueError("counts must be non-negative")
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1 = a + b
    col1 = a + c
    if row1 == 0 or col1 == 0 or row1 == n or col1 == n:
        return 1.0

    def log_p(x: int) -> float:
        # P(X = x) under Hypergeometric(n, col1, row1)
        return (
            math.lgamma(row1 + 1)
            - math.lgamma(x + 1)
            - math.lgamma(row1 - x + 1)
            + math.lgamma(n - row1 + 1)
            - math.lgamma(col1 - x + 1)
            - math.lgamma(n - row1 - col1 + x + 1)
            - (math.lgamma(n + 1) - math.lgamma(col1 + 1) - math.lgamma(n - col1 + 1))
        )

    observed = log_p(a)
    lo = max(0, row1 + col1 - n)
    hi = min(row1, col1)
    total = 0.0
    for x in range(lo, hi + 1):
        lp = log_p(x)
        if lp <= observed + 1e-12:
            total += math.exp(lp)
    return float(min(1.0, total))


def binomial_tail_p(k: int, n: int, p0: float) -> float:
    """One-sided exact binomial p-value ``P(X >= k | n, p0)``.

    Used to test a pre-registered threshold (e.g. stable yield > 0.1) without
    relying on a normal approximation at the sample sizes used here.
    """
    if n <= 0:
        return 1.0
    if not (0.0 <= p0 <= 1.0):
        raise ValueError("p0 must be in [0, 1]")
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    total = 0.0
    for x in range(k, n + 1):
        total += math.comb(n, x) * (p0 ** x) * ((1 - p0) ** (n - x))
    return float(min(1.0, total))


def bootstrap_p_value(
    diffs: List[float], n_boot: int = 2000, seed: int = 0
) -> float:
    """Two-sided percentile-bootstrap p-value for ``mean(diffs) == 0``.

    The bootstrap distribution of the mean is centred at zero under the null;
    the p-value is twice the smaller tail mass, clipped to ``[1/n_boot, 1]``.
    This is a resampling approximation, not an exact test, and must be
    reported as such.
    """
    if not diffs:
        return 1.0
    rng = np.random.default_rng(seed)
    arr = np.asarray(diffs, dtype=float)
    means = np.asarray(
        [float(np.mean(rng.choice(arr, size=len(arr), replace=True))) for _ in range(n_boot)]
    )
    centred = means - float(np.mean(arr))
    obs = abs(float(np.mean(arr)))
    p = float(np.mean(np.abs(centred) >= obs))
    return float(min(1.0, max(p, 1.0 / n_boot)))
