"""Tests for coverage-vector equivalence classes."""

import unittest

from fault_localization.models import CoverageMatrix, TestCoverage, TestVerdict
from fault_localization.tie_analysis import coverage_equivalence_classes


class CoverageEquivalenceTests(unittest.TestCase):
    def test_groups_identical_line_coverage_vectors(self) -> None:
        vectors = ((1, 1, 0), (1, 1, 0), (1, 0, 0))
        tests = tuple(
            TestCoverage(
                test_id=f"t{index}",
                verdict=(TestVerdict.FAIL if index == 0 else TestVerdict.PASS),
                covered_lines=tuple(
                    line + 10 for line, vector in enumerate(vectors) if vector[index]
                ),
                executable_lines=(10, 11, 12),
                exit_code=0,
                timed_out=False,
                gcov_version="test",
            )
            for index in range(3)
        )
        matrix = CoverageMatrix("case", "bug.c", (), "", "", tests)
        classes = coverage_equivalence_classes(matrix)
        self.assertEqual(2, len(classes))
        self.assertEqual(((1, 1, 0), (10, 11)), (
            classes[0].vector, classes[0].lines
        ))
        self.assertEqual(((1, 0, 0), (12,)), (
            classes[1].vector, classes[1].lines
        ))


if __name__ == "__main__":
    unittest.main()
