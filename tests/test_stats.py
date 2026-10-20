"""Tests for statistical estimators."""
import math
import unittest

from driveevidence.stats.estimators import (
    benjamini_hochberg,
    cohens_h,
    holm_correction,
    paired_bootstrap_ci,
    stable_failure_yield,
    wilson_ci,
)


class StatsTests(unittest.TestCase):
    def test_wilson_known_value(self):
        # k=10, n=100 should give interval around 0.055 to 0.176
        lo, hi = wilson_ci(10, 100)
        self.assertAlmostEqual(lo, 0.055, places=2)
        self.assertAlmostEqual(hi, 0.176, places=2)

    def test_wilson_zero_n(self):
        lo, hi = wilson_ci(0, 0)
        self.assertEqual(lo, 0.0)
        self.assertEqual(hi, 1.0)

    def test_wilson_full_success(self):
        lo, hi = wilson_ci(100, 100)
        self.assertLess(lo, 1.0)
        self.assertEqual(hi, 1.0)

    def test_wilson_full_failure(self):
        lo, hi = wilson_ci(0, 100)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_stable_yield(self):
        point, ci = stable_failure_yield(8, 64)
        self.assertEqual(point, 0.125)
        lo, centre, hi = ci
        self.assertAlmostEqual(centre, 0.125)
        self.assertLessEqual(lo, centre)
        self.assertGreaterEqual(hi, centre)

    def test_stable_yield_zero_nominated(self):
        point, ci = stable_failure_yield(0, 0)
        self.assertEqual(point, 0.0)
        self.assertEqual(ci, (0.0, 0.0, 1.0))

    def test_paired_bootstrap(self):
        diffs = [1.0] * 10 + [-1.0] * 10
        lo, hi = paired_bootstrap_ci(diffs, n_boot=1000, seed=123)
        self.assertLess(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_cohens_h(self):
        h = cohens_h(0.5, 0.3)
        self.assertGreater(h, 0.0)
        self.assertAlmostEqual(cohens_h(0.0, 0.0), 0.0, places=6)

    def test_holm_order(self):
        pvals = [0.01, 0.04, 0.03, 0.50]
        adj = holm_correction(pvals)
        self.assertEqual(len(adj), 4)
        self.assertLessEqual(adj[0], adj[1])
        self.assertLessEqual(adj[1], adj[3])
        self.assertTrue(all(0 <= a <= 1 for a in adj))

    def test_holm_sorted_input(self):
        pvals = [0.01, 0.02, 0.03]
        adj = holm_correction(pvals)
        # Sorted ascending; Holm adjusted = [0.01*3, max(prev, 0.02*2), max(prev, 0.03)]
        self.assertAlmostEqual(adj[0], 0.03, places=5)
        self.assertAlmostEqual(adj[1], 0.04, places=5)
        self.assertAlmostEqual(adj[2], 0.04, places=5)

    def test_benjamini_hochberg_monotonic(self):
        pvals = [0.005, 0.02, 0.04, 0.10]
        adj = benjamini_hochberg(pvals)
        self.assertEqual(len(adj), 4)
        for i in range(1, len(adj)):
            self.assertLessEqual(adj[i - 1], adj[i])
        self.assertTrue(all(0 <= a <= 1 for a in adj))


if __name__ == "__main__":
    unittest.main()


class TestNewcombeAndFisher(unittest.TestCase):
    """Tests for the proportion-difference CI and exact test added for protocol v2."""

    def test_newcombe_brackets_point_estimate(self):
        from driveevidence.stats.estimators import newcombe_diff_ci

        diff, lo, hi = newcombe_diff_ci(40, 64, 48, 64)
        self.assertAlmostEqual(diff, 0.125, places=6)
        self.assertLessEqual(lo, diff)
        self.assertGreaterEqual(hi, diff)
        self.assertLess(lo, 0)

    def test_newcombe_symmetric_when_equal(self):
        from driveevidence.stats.estimators import newcombe_diff_ci

        diff, lo, hi = newcombe_diff_ci(32, 64, 32, 64)
        self.assertAlmostEqual(diff, 0.0, places=12)
        self.assertAlmostEqual(lo, -hi, places=9)

    def test_newcombe_degenerate(self):
        from driveevidence.stats.estimators import newcombe_diff_ci

        self.assertEqual(newcombe_diff_ci(0, 0, 5, 10), (0.0, -1.0, 1.0))

    def test_fisher_known_value(self):
        from driveevidence.stats.estimators import fisher_exact_two_sided

        # [[10,0],[0,10]] -> p = 2 / C(20,10) = 2/184756
        p = fisher_exact_two_sided(10, 0, 0, 10)
        self.assertAlmostEqual(p, 2 / 184756, places=9)

    def test_fisher_null_table_is_one(self):
        from driveevidence.stats.estimators import fisher_exact_two_sided

        self.assertAlmostEqual(fisher_exact_two_sided(5, 5, 5, 5), 1.0, places=9)

    def test_fisher_symmetry(self):
        from driveevidence.stats.estimators import fisher_exact_two_sided

        self.assertAlmostEqual(
            fisher_exact_two_sided(9, 3, 2, 10),
            fisher_exact_two_sided(2, 10, 9, 3),
            places=9,
        )


class TestBinomialAndBootstrapP(unittest.TestCase):
    def test_binomial_tail_known(self):
        from driveevidence.stats.estimators import binomial_tail_p

        # P(X >= 10 | n=10, p0=0.5) = 1/1024
        self.assertAlmostEqual(binomial_tail_p(10, 10, 0.5), 1 / 1024, places=12)

    def test_binomial_tail_monotone(self):
        from driveevidence.stats.estimators import binomial_tail_p

        self.assertGreater(binomial_tail_p(5, 20, 0.5), binomial_tail_p(12, 20, 0.5))

    def test_binomial_edge_cases(self):
        from driveevidence.stats.estimators import binomial_tail_p

        self.assertEqual(binomial_tail_p(0, 10, 0.1), 1.0)
        self.assertEqual(binomial_tail_p(5, 0, 0.1), 1.0)

    def test_bootstrap_p_null_is_large(self):
        from driveevidence.stats.estimators import bootstrap_p_value

        p = bootstrap_p_value([0.0] * 30, n_boot=500, seed=1)
        self.assertGreater(p, 0.5)

    def test_bootstrap_p_signal_is_small(self):
        from driveevidence.stats.estimators import bootstrap_p_value

        p = bootstrap_p_value([1.0] * 30, n_boot=500, seed=1)
        self.assertLess(p, 0.01)
