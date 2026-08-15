"""Tests for independent-evaluation grouping and leakage boundaries."""

import unittest

from fault_localization.independent_evaluation import (
    artifact_leakage_keys,
    coverage_diversity_group,
    fault_class_group,
    has_straight_line_ambiguity,
    is_non_executable_fault,
    pass_test_group,
    repair_test_group,
)
from fault_localization.models import RankedLine


class IndependentEvaluationTests(unittest.TestCase):
    def test_subgroup_boundaries(self) -> None:
        self.assertEqual("1-2", repair_test_group(2))
        self.assertEqual("3-5", repair_test_group(3))
        self.assertEqual("6+", repair_test_group(6))
        self.assertEqual("0 PASS", pass_test_group(0))
        self.assertEqual(">=1 PASS", pass_test_group(1))
        self.assertEqual("low (<=0.25)", coverage_diversity_group(0.25))
        self.assertEqual("medium (0.25-0.5)", coverage_diversity_group(0.5))
        self.assertEqual("high (>0.5)", coverage_diversity_group(0.51))
        self.assertEqual("non-executable", fault_class_group(None))
        self.assertEqual("1", fault_class_group(1))
        self.assertEqual("2-5", fault_class_group(5))
        self.assertEqual("6-10", fault_class_group(10))
        self.assertEqual(">10", fault_class_group(11))

    def test_leakage_scan_recurses_over_artifact_keys(self) -> None:
        self.assertEqual(
            {"validation_tests", "ground_truth_fault_lines"},
            artifact_leakage_keys(
                {"tests": {"validation_tests": []}, "ground_truth_fault_lines": [3]}
            ),
        )
        self.assertEqual(set(), artifact_leakage_keys({"covered_lines": [3]}))

    def test_non_executable_ground_truth(self) -> None:
        self.assertTrue(is_non_executable_fault((4,), {1, 2, 3}))
        self.assertFalse(is_non_executable_fault((3, 4), {1, 2, 3}))

    def test_straight_line_ambiguity_requires_same_final_tie_and_vector(self) -> None:
        def ranked(line: int, rank: int, start: int, end: int) -> RankedLine:
            return RankedLine(
                line=line,
                rank=rank,
                score=1.0,
                ef=1,
                ep=0,
                nf=0,
                np=1,
                source_snippet="statement",
                tie_start_rank=start,
                tie_end_rank=end,
            )

        ranking = (
            ranked(4, 1, 1, 2),
            ranked(5, 2, 1, 2),
            ranked(6, 3, 3, 3),
        )
        self.assertTrue(
            has_straight_line_ambiguity(
                (4,), ranking, {4: (1, 0), 5: (1, 0), 6: (1, 0)}
            )
        )
        self.assertFalse(
            has_straight_line_ambiguity(
                (4,), ranking, {4: (1, 0), 5: (0, 1), 6: (1, 0)}
            )
        )


if __name__ == "__main__":
    unittest.main()
