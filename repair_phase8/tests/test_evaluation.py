import unittest

from repair.models import PatchClassification, PatchEvaluation, TestResult
from repair_phase8.evaluation import second_round_eligibility
from repair_phase8.partition import partitioned_case, derive_partition
from repair_phase8.tests.test_partition import make_case


def result(
    base: bool = True,
    feedback: bool = True,
    hidden: bool = True,
    compile_success: bool = True,
    feedback_id: str = "v0",
) -> PatchEvaluation:
    repair = (
        TestResult("base", base, "", "", 0, False),
        TestResult(feedback_id, feedback, "", "", 0, False),
    )
    validation = (TestResult("v1", hidden, "", "", 0, False),) if base and feedback else ()
    plausible = compile_success and base and feedback
    validated = plausible and hidden
    classification = (
        PatchClassification.COMPILE_ERROR
        if not compile_success
        else PatchClassification.REPAIR_TEST_FAILED
        if not plausible
        else PatchClassification.VALIDATED_PATCH
        if validated
        else PatchClassification.PLAUSIBLE_PATCH
    )
    return PatchEvaluation(
        compile_success,
        "",
        "compiler error" if not compile_success else "",
        0 if compile_success else 1,
        repair if compile_success else (),
        validation,
        plausible,
        validated,
        classification,
        (),
    )


class EligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        original = make_case(validation_count=2)
        partition = derive_partition(original, 20260820)
        self.case = partitioned_case(original, partition)
        self.feedback_id = self.case.metadata["phase8"]["feedback_test_ids"][0]

    def test_compile_base_and_feedback_failures_are_eligible(self) -> None:
        self.assertTrue(
            second_round_eligibility(
                self.case, result(compile_success=False, feedback_id=self.feedback_id)
            ).eligible
        )
        self.assertEqual(
            "base_repair_test_failure",
            second_round_eligibility(
                self.case, result(base=False, feedback_id=self.feedback_id)
            ).reason,
        )
        self.assertEqual(
            "feedback_test_failure",
            second_round_eligibility(
                self.case, result(feedback=False, feedback_id=self.feedback_id)
            ).reason,
        )

    def test_hidden_only_failure_never_triggers_second_round(self) -> None:
        decision = second_round_eligibility(
            self.case, result(hidden=False, feedback_id=self.feedback_id)
        )
        self.assertFalse(decision.eligible)
        self.assertEqual("repair_time_success", decision.reason)

    def test_provider_and_invalid_output_are_not_eligible(self) -> None:
        self.assertFalse(second_round_eligibility(self.case, None, provider_failed=True).eligible)
        self.assertFalse(
            second_round_eligibility(self.case, None, invalid_model_output=True).eligible
        )


if __name__ == "__main__":
    unittest.main()
