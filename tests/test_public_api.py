"""Public API surface tests.

Guards the package-level exports (``__all__``) so a refactor cannot silently
break the documented import paths.  These are intentionally shallow: they assert
the symbol resolves and is the expected kind, not that every function works
(behaviour is covered by the per-module tests).
"""

from __future__ import annotations

import unittest


class TestPublicApiExports(unittest.TestCase):
    def test_version_is_consistent_with_metadata(self):
        import driveevidence
        from importlib.metadata import version

        # In an installed (or `pip install -e`) environment the module version
        # must equal the distribution version.
        self.assertEqual(driveevidence.__version__, version("driveevidence"))

    def test_scenario_exports(self):
        from driveevidence.scenario import (
            IR_VERSION,
            ScenarioIR,
            ScenarioValidationError,
            VehicleState,
        )

        self.assertEqual(IR_VERSION, "ir/v1")
        self.assertTrue(issubclass(ScenarioValidationError, ValueError))
        self.assertTrue(all(x is not None for x in (ScenarioIR, VehicleState)))

    def test_sim_exports(self):
        from driveevidence.sim import (
            EpisodeResult,
            FailureCategory,
            SimulatorAdapter,
            TrajectorySample,
            create_adapter,
            list_adapters,
            register_adapter,
        )

        self.assertIn("builtin", list_adapters())
        self.assertTrue(callable(create_adapter))
        self.assertTrue(callable(register_adapter))
        for sym in (EpisodeResult, FailureCategory, SimulatorAdapter, TrajectorySample):
            self.assertIsNotNone(sym)

    def test_search_exports(self):
        from driveevidence.search import (
            BaseSearchMethod,
            Budget,
            FailureCandidate,
            MutationSearch,
            RandomSearch,
            SearchReport,
        )

        self.assertTrue(issubclass(RandomSearch, BaseSearchMethod))
        self.assertTrue(issubclass(MutationSearch, BaseSearchMethod))
        for sym in (Budget, FailureCandidate, SearchReport):
            self.assertIsNotNone(sym)

    def test_planner_exports(self):
        from driveevidence.planners import (
            PlannerContext,
            PlannerFn,
            default_planner,
            get_planner,
            list_planners,
        )

        self.assertIn("safe_follow", list_planners())
        self.assertEqual(default_planner(), "safe_follow")
        self.assertTrue(callable(get_planner))
        self.assertIsNotNone(PlannerContext)
        self.assertIsNotNone(PlannerFn)

    def test_stats_exports(self):
        from driveevidence.stats import (
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

        for fn in (
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
        ):
            self.assertTrue(callable(fn))

    def test_report_exports(self):
        from driveevidence.report import (
            ReportSummary,
            generate_html,
            generate_markdown,
            load_report,
        )

        self.assertTrue(callable(load_report))
        self.assertTrue(callable(generate_markdown))
        self.assertTrue(callable(generate_html))
        self.assertIsNotNone(ReportSummary)

    def test_evidence_exports(self):
        from driveevidence.evidence import (
            DrivingEvidenceRecorder,
            EpisodeStore,
            ReplayOutcome,
            RunLedger,
            build_manifest,
            replay_episode,
            verify_manifest,
        )

        for sym in (
            DrivingEvidenceRecorder,
            EpisodeStore,
            ReplayOutcome,
            RunLedger,
            build_manifest,
            replay_episode,
            verify_manifest,
        ):
            self.assertIsNotNone(sym)


if __name__ == "__main__":
    unittest.main()
