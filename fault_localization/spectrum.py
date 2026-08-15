"""Build ef/ep/nf/np spectra from a repair-test coverage matrix."""

from .models import CoverageMatrix, SpectrumLine, TestVerdict


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
