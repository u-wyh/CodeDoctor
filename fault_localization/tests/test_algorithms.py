"""Hand-computed tests for spectrum construction and SBFL formulas."""

import math
import sys
import unittest

from fault_localization.algorithms import dstar2, ochiai, tarantula
from fault_localization.models import (
    BranchCoverage,
    CoverageMatrix,
    SpectrumLine,
    SpectrumBranch,
    TestCoverage,
    TestVerdict,
)
from fault_localization.spectrum import build_branch_spectrum, build_spectrum


def _test(test_id: str, verdict: TestVerdict, covered: tuple[int, ...]) -> TestCoverage:
    return TestCoverage(
        test_id=test_id,
        verdict=verdict,
        covered_lines=covered,
        executable_lines=(10, 11, 12),
        exit_code=0,
        timed_out=False,
        gcov_version="test",
    )


class SpectrumTests(unittest.TestCase):
    def test_builds_hand_computed_counts(self) -> None:
        matrix = CoverageMatrix(
            case_id="case",
            source_path="bug.c",
            compile_command=(),
            compile_stdout="",
            compile_stderr="",
            tests=(
                _test("fail", TestVerdict.FAIL, (10, 11)),
                _test("pass", TestVerdict.PASS, (10,)),
            ),
        )
        self.assertEqual(
            (
                SpectrumLine(10, ef=1, ep=1, nf=0, np=0),
                SpectrumLine(11, ef=1, ep=0, nf=0, np=1),
                SpectrumLine(12, ef=0, ep=0, nf=1, np=1),
            ),
            build_spectrum(matrix),
        )

    def test_builds_branch_spectrum_by_taken_outcome(self) -> None:
        failed = _test("fail", TestVerdict.FAIL, (10,))
        passed = _test("pass", TestVerdict.PASS, (10,))
        failed = TestCoverage(
            **{**failed.__dict__, "branches": (
                BranchCoverage(10, 0, 3, True, True, False),
                BranchCoverage(10, 1, 0, False, False, False),
            )}
        )
        passed = TestCoverage(
            **{**passed.__dict__, "branches": (
                BranchCoverage(10, 0, 0, False, True, False),
                BranchCoverage(10, 1, 1, True, False, False),
            )}
        )
        matrix = CoverageMatrix("case", "bug.c", (), "", "", (failed, passed))
        self.assertEqual(
            (
                SpectrumBranch(10, 0, ef=1, ep=0, nf=0, np=1),
                SpectrumBranch(10, 1, ef=0, ep=1, nf=1, np=0),
            ),
            build_branch_spectrum(matrix),
        )


class FormulaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spectrum = SpectrumLine(37, ef=2, ep=1, nf=1, np=3)

    def test_ochiai_matches_manual_result(self) -> None:
        self.assertAlmostEqual(2 / 3, ochiai(self.spectrum))

    def test_tarantula_matches_manual_result(self) -> None:
        self.assertAlmostEqual(8 / 11, tarantula(self.spectrum))

    def test_dstar2_matches_manual_result(self) -> None:
        self.assertEqual(2.0, dstar2(self.spectrum))

    def test_zero_denominators_are_explicit(self) -> None:
        empty = SpectrumLine(1, ef=0, ep=0, nf=0, np=0)
        isolated_failure = SpectrumLine(2, ef=1, ep=0, nf=0, np=2)
        self.assertEqual(0.0, ochiai(empty))
        self.assertEqual(0.0, tarantula(empty))
        self.assertEqual(0.0, dstar2(empty))
        self.assertEqual(sys.float_info.max, dstar2(isolated_failure))
        self.assertTrue(math.isfinite(dstar2(isolated_failure)))


if __name__ == "__main__":
    unittest.main()
