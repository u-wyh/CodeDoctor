"""Tests for localization status boundaries and repair-time data isolation."""

import unittest

from benchmark.models import (
    BenchmarkCase,
    BenchmarkTest,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)
from fault_localization.models import (
    CoverageMatrix,
    LocalizationInput,
    TestCoverage,
    TestVerdict,
)
from fault_localization.pipeline import localize


def _coverage(test_id: str, verdict: TestVerdict) -> TestCoverage:
    return TestCoverage(test_id, verdict, (2,), (2, 3), 0, False, "test")


def _matrix(*tests: TestCoverage) -> CoverageMatrix:
    return CoverageMatrix("case", "bug.c", (), "", "", tuple(tests))


class PipelineTests(unittest.TestCase):
    def test_no_failing_repair_test_has_required_status(self) -> None:
        result = localize(_matrix(_coverage("p1", TestVerdict.PASS)), "a\nb\nc\n")
        self.assertEqual(
            "not_localizable_no_failing_repair_test", result["status"]
        )
        self.assertEqual({}, result["rankings"])

    def test_all_failing_tests_are_ranked_with_warning(self) -> None:
        result = localize(_matrix(_coverage("n1", TestVerdict.FAIL)), "a\nb\nc\n")
        self.assertEqual("localizable", result["status"])
        self.assertEqual(["no_passing_repair_test"], result["warnings"])
        self.assertTrue(result["rankings"]["ochiai"])

    def test_localization_input_excludes_evaluation_only_data(self) -> None:
        case = BenchmarkCase(
            case_id="case",
            dataset="codeflaws",
            language="c",
            problem=ProblemIdentity("1", "A"),
            buggy=ProgramArtifact("bug.c", "1"),
            reference=ProgramArtifact("secret-reference.c", "2"),
            tests=TestSuites(
                (BenchmarkTest("p1", "in", "out"),),
                (BenchmarkTest("heldout", "held-in", "held-out"),),
            ),
            metadata={
                "defect_class": "test",
                "original_dataset_path": "raw/case",
            },
        )
        value = LocalizationInput.from_benchmark_case(case)
        self.assertFalse(hasattr(value, "reference"))
        self.assertFalse(hasattr(value, "validation_tests"))
        self.assertNotIn("secret-reference", repr(value))
        self.assertNotIn("heldout", repr(value))

    def test_coverage_matrix_json_round_trip(self) -> None:
        matrix = _matrix(
            _coverage("p1", TestVerdict.PASS),
            _coverage("n1", TestVerdict.FAIL),
        )
        self.assertEqual(matrix, CoverageMatrix.from_dict(matrix.to_dict()))


if __name__ == "__main__":
    unittest.main()
