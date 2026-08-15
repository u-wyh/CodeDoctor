"""Repair-time-only coverage-to-ranking fault localization pipeline."""

import json
from dataclasses import asdict
from typing import Any

from .algorithms import ALGORITHMS
from .models import CoverageMatrix
from .ranking import rank_spectrum
from .spectrum import build_spectrum


def localize(matrix: CoverageMatrix, buggy_source: str) -> dict[str, Any]:
    if matrix.failed_tests == 0:
        return {
            "case_id": matrix.case_id,
            "status": "not_localizable_no_failing_repair_test",
            "passed_tests": matrix.passed_tests,
            "failed_tests": matrix.failed_tests,
            "executable_lines": len(matrix.executable_lines),
            "spectrum": [],
            "rankings": {},
        }
    spectrum = build_spectrum(matrix)
    rankings = {
        name: [asdict(item) for item in rank_spectrum(spectrum, formula, buggy_source)]
        for name, formula in ALGORITHMS.items()
    }
    return {
        "case_id": matrix.case_id,
        "status": "localizable",
        "passed_tests": matrix.passed_tests,
        "failed_tests": matrix.failed_tests,
        "warnings": (
            ["no_passing_repair_test"] if matrix.passed_tests == 0 else []
        ),
        "executable_lines": len(matrix.executable_lines),
        "spectrum": [asdict(item) for item in spectrum],
        "rankings": json.loads(json.dumps(rankings)),
    }
