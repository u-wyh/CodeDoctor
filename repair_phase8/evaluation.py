"""Phase 8 repair-time eligibility independent of hidden validation outcomes."""

from benchmark.models import BenchmarkCase
from repair.models import PatchEvaluation

from .models import EligibilityDecision


def second_round_eligibility(
    case: BenchmarkCase,
    evaluation: PatchEvaluation | None,
    *,
    provider_failed: bool = False,
    invalid_model_output: bool = False,
) -> EligibilityDecision:
    if provider_failed:
        return EligibilityDecision(False, "provider_failure")
    if invalid_model_output:
        return EligibilityDecision(False, "invalid_model_output")
    if evaluation is None:
        raise ValueError("patch evaluation is required for an extracted source")
    if not evaluation.compile_success:
        return EligibilityDecision(True, "compile_failure")
    phase8 = case.metadata["phase8"]
    base_ids = set(phase8["base_test_ids"])
    feedback_ids = set(phase8["feedback_test_ids"])
    failed = {item.test_id for item in evaluation.repair_tests if not item.passed}
    failed_base = tuple(sorted(failed & base_ids))
    failed_feedback = tuple(sorted(failed & feedback_ids))
    if failed_base or failed_feedback:
        reason = (
            "base_and_feedback_test_failure"
            if failed_base and failed_feedback
            else "base_repair_test_failure"
            if failed_base
            else "feedback_test_failure"
        )
        return EligibilityDecision(True, reason, failed_base, failed_feedback)
    return EligibilityDecision(False, "repair_time_success")
