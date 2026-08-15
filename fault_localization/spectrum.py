"""Build ef/ep/nf/np spectra from a repair-test coverage matrix."""

from .models import (
    CoverageMatrix,
    SpectrumBranch,
    SpectrumLine,
    TestCoverage,
    TestVerdict,
)


def build_spectrum(matrix: CoverageMatrix) -> tuple[SpectrumLine, ...]:
    passed = tuple(
        test for test in matrix.tests if test.verdict is TestVerdict.PASS
    )
    failed = tuple(
        test for test in matrix.tests if test.verdict is TestVerdict.FAIL
    )
    records = []
    for line in matrix.executable_lines:
        ef = sum(line in test.covered_lines for test in failed)
        ep = sum(line in test.covered_lines for test in passed)
        records.append(
            SpectrumLine(
                line=line,
                ef=ef,
                ep=ep,
                nf=len(failed) - ef,
                np=len(passed) - ep,
            )
        )
    return tuple(records)


def build_branch_spectrum(matrix: CoverageMatrix) -> tuple[SpectrumBranch, ...]:
    passed = tuple(
        test for test in matrix.tests if test.verdict is TestVerdict.PASS
    )
    failed = tuple(
        test for test in matrix.tests if test.verdict is TestVerdict.FAIL
    )

    def taken(test: TestCoverage, key: tuple[int, int]) -> bool:
        return any(
            (branch.line, branch.branch_index) == key and branch.taken
            for branch in test.branches
        )

    records = []
    for line, branch_index in matrix.executable_branches:
        key = (line, branch_index)
        ef = sum(taken(test, key) for test in failed)
        ep = sum(taken(test, key) for test in passed)
        records.append(
            SpectrumBranch(
                line=line,
                branch_index=branch_index,
                ef=ef,
                ep=ep,
                nf=len(failed) - ef,
                np=len(passed) - ep,
            )
        )
    return tuple(records)
