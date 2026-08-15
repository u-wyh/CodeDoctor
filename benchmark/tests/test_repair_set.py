"""Repair Pilot disjointness and deterministic eligibility tests."""

import unittest

from benchmark.execution import CaseVerification, CompileVerification, SuiteVerification
from benchmark.models import BenchmarkCase, ProblemIdentity, ProgramArtifact, TestSuites
from benchmark.repair_set import repair_candidate_order, repair_eligibility_reason


def case(case_id: str, defect_class: str) -> BenchmarkCase:
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


def verification(failed: int) -> CaseVerification:
    compile_result = CompileVerification(True, 0, False, 1, "", "")
    reference = SuiteVerification(1, 1, 0, 0, 0, None)
    buggy = SuiteVerification(2, 2 - failed, failed, 0, 0, "n" if failed else None)
    return CaseVerification(
        "case", "DCCR", compile_result, compile_result, reference, reference,
        buggy, None, True, None
    )


class RepairSetTests(unittest.TestCase):
    def test_order_excludes_both_prior_sets_and_is_reproducible(self) -> None:
        cases = [case("pilot", "A"), case("eval", "B"), case("x", "A"), case("y", "B")]
        excluded = {"pilot", "eval"}
        first = repair_candidate_order(cases, excluded, 20260817)
        second = repair_candidate_order(reversed(cases), excluded, 20260817)
        self.assertEqual(["x", "y"], [item.case_id for item in first])
        self.assertEqual(
            [item.case_id for item in first], [item.case_id for item in second]
        )

    def test_eligibility_requires_failing_repair_test(self) -> None:
        self.assertIsNone(repair_eligibility_reason(verification(1)))
        self.assertEqual(
            "buggy_no_failing_repair_test",
            repair_eligibility_reason(verification(0)),
        )


if __name__ == "__main__":
    unittest.main()
