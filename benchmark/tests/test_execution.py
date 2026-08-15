"""Unit tests for benchmark output semantics and stratified ordering."""

import unittest

from benchmark.execution import outputs_equivalent
from benchmark.models import (
    BenchmarkCase,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)
from benchmark.sampling import stratified_case_order


def _case(case_id: str, defect_class: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        dataset="codeflaws",
        language="c",
        problem=ProblemIdentity("1", "A"),
        buggy=ProgramArtifact("bug.c", "1"),
        reference=ProgramArtifact("ref.c", "2"),
        tests=TestSuites((), ()),
        metadata={"defect_class": defect_class},
    )


class OutputComparisonTests(unittest.TestCase):
    def test_matches_codeflaws_whitespace_rules(self) -> None:
        self.assertTrue(
            outputs_equivalent(
                b"\n    42   \n", b"42\n", strip_leading_space=True
            )
        )

    def test_preserves_leading_space_when_script_does(self) -> None:
        self.assertFalse(
            outputs_equivalent(
                b" 42\n", b"42\n", strip_leading_space=False
            )
        )


class StratifiedSamplingTests(unittest.TestCase):
    def test_round_robins_classes_deterministically(self) -> None:
        cases = [
            _case("a1", "A"),
            _case("a2", "A"),
            _case("b1", "B"),
            _case("b2", "B"),
        ]
        first = stratified_case_order(cases, 20260815)
        second = stratified_case_order(reversed(cases), 20260815)
        self.assertEqual([case.case_id for case in first], [case.case_id for case in second])
        self.assertEqual(["A", "B", "A", "B"], [case.metadata["defect_class"] for case in first])


if __name__ == "__main__":
    unittest.main()
