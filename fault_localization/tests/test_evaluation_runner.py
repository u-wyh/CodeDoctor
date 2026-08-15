"""Tests for the frozen independent-evaluation ranking boundary."""

import unittest

from benchmark.scripts.run_fault_localization_evaluation import (
    EVALUATED_METHODS,
    _fl_v1_ranking,
)
from fault_localization.models import CoverageMatrix, TestCoverage, TestVerdict


class EvaluationRunnerTests(unittest.TestCase):
    def test_writes_only_preregistered_methods(self) -> None:
        matrix = CoverageMatrix(
            "case",
            "bug.c",
            (),
            "",
            "",
            (
                TestCoverage("n1", TestVerdict.FAIL, (2,), (2,), 0, False, "test"),
            ),
        )
        result = _fl_v1_ranking(matrix, "int main() {\nreturn 1;\n}\n")
        self.assertEqual("fl-v1", result["method_version"])
        self.assertEqual(set(EVALUATED_METHODS), set(result["rankings"]))


if __name__ == "__main__":
    unittest.main()
