"""Repair-time-only coverage-to-ranking fault localization pipeline."""

import json
from dataclasses import asdict
from typing import Any

from .algorithms import ALGORITHMS, ochiai
from .models import CoverageMatrix
from .ranking import rank_spectrum, rank_with_branch_tiebreak
from .spectrum import build_branch_spectrum, build_spectrum
from .tie_analysis import coverage_equivalence_classes


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
    branch_spectrum = build_branch_spectrum(matrix)
    branch_scores: dict[int, float] = {}
    for item in branch_spectrum:
        branch_scores[item.line] = max(
            branch_scores.get(item.line, 0.0), ochiai(item)
        )
    rankings = {
        name: [asdict(item) for item in rank_spectrum(spectrum, formula, buggy_source)]
        for name, formula in ALGORITHMS.items()
    }
    rankings["ochiai_branch_tiebreak"] = [
        asdict(item)
        for item in rank_with_branch_tiebreak(
            spectrum, ochiai, branch_scores, buggy_source
        )
    ]
    equivalence_classes = coverage_equivalence_classes(matrix)
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
        "branch_outcomes": len(matrix.executable_branches),
        "branch_spectrum": [
            {**asdict(item), "score": ochiai(item)} for item in branch_spectrum
        ],
        "branch_line_scores": {
            str(line): score for line, score in sorted(branch_scores.items())
        },
        "coverage_equivalence_classes": [
            asdict(item) for item in equivalence_classes
        ],
        "rankings": json.loads(json.dumps(rankings)),
    }
