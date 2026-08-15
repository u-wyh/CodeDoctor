"""Disjoint Repair Pilot selection built on the existing eligibility rules."""

import json
from dataclasses import asdict
from typing import Iterable

from .evaluation_set import evaluation_eligibility_reason
from .execution import CaseVerification
from .models import BenchmarkCase
from .sampling import stratified_case_order


def repair_candidate_order(
    cases: Iterable[BenchmarkCase], excluded_ids: set[str], seed: int
) -> list[BenchmarkCase]:
    return stratified_case_order(
        (case for case in cases if case.case_id not in excluded_ids), seed
    )


def repair_eligibility_reason(verification: CaseVerification) -> str | None:
    return evaluation_eligibility_reason(verification)


def repair_record(
    case: BenchmarkCase,
    verification: CaseVerification,
    *,
    seed: int,
    candidate_index: int,
) -> dict[str, object]:
    value = case.to_dict()
    value["metadata"]["repair_pilot"] = {
        "candidate_index": candidate_index,
        "docker_verified": True,
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


def repair_verification_record(
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
