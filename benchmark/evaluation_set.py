"""Independent Codeflaws evaluation-set selection and eligibility rules."""

import json
from dataclasses import asdict
from typing import Iterable

from .execution import CaseVerification
from .models import BenchmarkCase
from .sampling import stratified_case_order


def independent_candidate_order(
    cases: Iterable[BenchmarkCase],
    pilot_ids: set[str],
    seed: int,
) -> list[BenchmarkCase]:
    return stratified_case_order(
        (case for case in cases if case.case_id not in pilot_ids), seed
    )


def evaluation_eligibility_reason(
    verification: CaseVerification,
) -> str | None:
    if not verification.reproducible:
        return verification.exclusion_reason or "dynamic_verification_failed"
    if verification.buggy_repair is None:
        return "buggy_repair_not_executed"
    if verification.buggy_repair.failed == 0:
        return "buggy_no_failing_repair_test"
    return None


def evaluation_record(
    case: BenchmarkCase,
    verification: CaseVerification,
    *,
    seed: int,
    candidate_index: int,
) -> dict[str, object]:
    value = case.to_dict()
    value["metadata"]["fl_evaluation"] = {
        "candidate_index": candidate_index,
        "docker_verified": True,
        "method_version": "fl-v1",
        "seed": seed,
        "verification": {
            "buggy_compile": verification.buggy_compile.success,
            "buggy_repair_failed": verification.buggy_repair.failed,
            "buggy_repair_passed": verification.buggy_repair.passed,
            "reference_compile": verification.reference_compile.success,
            "reference_repair_passed": verification.reference_repair.passed,
            "reference_validation_passed": verification.reference_validation.passed,
        },
    }
    return json.loads(json.dumps(value))


def verification_record(
    verification: CaseVerification,
    *,
    seed: int,
    candidate_index: int,
    eligibility_reason: str | None,
) -> dict[str, object]:
    value = asdict(verification)
    value.update(
        {
            "candidate_index": candidate_index,
            "eligibility_reason": eligibility_reason,
            "seed": seed,
        }
    )
    return json.loads(json.dumps(value))
