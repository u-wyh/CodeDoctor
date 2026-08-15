"""Tests for independent FL evaluation-set selection and eligibility."""

import unittest

from benchmark.evaluation_set import (
    evaluation_eligibility_reason,
    independent_candidate_order,
)
from benchmark.execution import (
    CaseVerification,
    CompileVerification,
    SuiteVerification,
)
from benchmark.models import (
    BenchmarkCase,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)


def _case(case_id: str, defect_class: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id,
        "codeflaws",
        "c",
        ProblemIdentity("1", "A"),
        ProgramArtifact("bug.c", "1"),
        ProgramArtifact("ref.c", "2"),
        TestSuites((), ()),
        {"defect_class": defect_class},
    )


def _verification(*, buggy_failed: int, reproducible: bool = True) -> CaseVerification:
    compiled = CompileVerification(True, 0, False, 1, "", "")
    reference = SuiteVerification(2, 2, 0, 0, 0, None)
    buggy = SuiteVerification(
        2,
        2 - buggy_failed,
        buggy_failed,
        0,
        0,
        "n1" if buggy_failed else None,
    )
    return CaseVerification(
        "case",
        "DCCR",
        compiled,
        compiled,
        reference,
        reference,
        buggy,
        None,
        reproducible,
        None if reproducible else "reference_failed_validation_tests",
    )


class EvaluationSetTests(unittest.TestCase):
    def test_split_excludes_pilot_and_is_seed_reproducible(self) -> None:
        cases = [_case("p", "A"), _case("a", "A"), _case("b", "B")]
        first = independent_candidate_order(cases, {"p"}, 20260816)
        second = independent_candidate_order(reversed(cases), {"p"}, 20260816)
        self.assertEqual(["a", "b"], [case.case_id for case in first])
        self.assertEqual(
            [case.case_id for case in first], [case.case_id for case in second]
        )

    def test_eligibility_requires_a_failing_buggy_repair_test(self) -> None:
        self.assertIsNone(
            evaluation_eligibility_reason(_verification(buggy_failed=1))
        )
        self.assertEqual(
            "buggy_no_failing_repair_test",
            evaluation_eligibility_reason(_verification(buggy_failed=0)),
        )
        self.assertEqual(
            "reference_failed_validation_tests",
            evaluation_eligibility_reason(
                _verification(buggy_failed=1, reproducible=False)
            ),
        )


if __name__ == "__main__":
    unittest.main()
