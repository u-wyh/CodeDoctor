"""Reference filtering and V3/V4 patch validation for Phase 9."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from benchmark.config import PROJECT_ROOT
from benchmark.models import BenchmarkCase
from repair_phase8.partition import canonical_hash

from .batch import BatchObservation, BatchResult, DockerBatchExecutor
from .mutation import MutationCandidate, generate_numeric_mutations


def _read(relative_path: str | None) -> str:
    if relative_path is None:
        return ""
    path = (PROJECT_ROOT / relative_path).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"Phase 9 input escapes project root: {relative_path}")
    return path.read_text(encoding="utf-8", errors="replace")


def official_inputs(case: BenchmarkCase) -> list[tuple[str, str]]:
    values = []
    for suite, tests in (
        ("repair", case.tests.repair_tests),
        ("hidden", case.tests.validation_tests),
    ):
        for index, test in enumerate(tests):
            values.append(
                (f"{suite}/{index:04d}/{test.test_id}", _read(test.input_path))
            )
    return values


def sanitizer_failure_type(observation: BatchObservation) -> str | None:
    if observation.timed_out:
        return "sanitizer_timeout"
    findings = observation.sanitizer_findings
    if "asan" in findings or "lsan" in findings:
        return "ASan"
    if "ubsan" in findings:
        return "UBSan"
    if observation.exit_code != 0:
        return "sanitizer_abnormal_exit"
    return None


def differential_failure_type(
    observation: BatchObservation, expected_hash: str
) -> str | None:
    if observation.timed_out:
        return "differential_timeout"
    if observation.exit_code != 0:
        return "differential_runtime_error"
    if observation.stdout_hash != expected_hash:
        return "differential_output_mismatch"
    return None


def accept_reference_candidates(
    candidates: Sequence[MutationCandidate],
    first: BatchResult,
    second: BatchResult,
    sanitizer: BatchResult,
    *,
    acceptance_cap: int = 100,
    start_index: int = 0,
) -> list[dict[str, Any]]:
    if not first.compile_success or not second.compile_success or not sanitizer.compile_success:
        return []
    first_by_id = {item.test_id: item for item in first.observations}
    second_by_id = {item.test_id: item for item in second.observations}
    sanitizer_by_id = {item.test_id: item for item in sanitizer.observations}
    accepted = []
    for index, candidate in enumerate(candidates):
        test_id = f"candidate/{start_index + index:06d}"
        one = first_by_id[test_id]
        two = second_by_id[test_id]
        sanitized = sanitizer_by_id[test_id]
        if (
            one.exit_code != 0
            or two.exit_code != 0
            or one.timed_out
            or two.timed_out
            or one.stdout_hash != two.stdout_hash
            or sanitizer_failure_type(sanitized) is not None
        ):
            continue
        accepted.append(
            {
                "generator_order_hash": candidate.order_hash,
                "input_hash": candidate.input_hash,
                "input_text": candidate.input_text,
                "mutation_value": candidate.mutation_value,
                "reference_determinism_hashes": [one.stdout_hash, two.stdout_hash],
                "reference_output_hash": one.stdout_hash,
                "reference_sanitizer_status": "clean",
                "source_test_id": candidate.source_test_id,
                "token_index": candidate.token_index,
            }
        )
        if len(accepted) == acceptance_cap:
            break
    return accepted


def run_reference_case(
    case: BenchmarkCase,
    executor: DockerBatchExecutor,
    *,
    seed: int,
    proposal_cap: int = 500,
    acceptance_cap: int = 100,
    execution_chunk_size: int = 128,
) -> dict[str, Any]:
    inputs = official_inputs(case)
    candidates = generate_numeric_mutations(
        case_id=case.case_id,
        seed=seed,
        seed_inputs=inputs,
        proposal_cap=proposal_cap,
    )
    source = case.get_reference_source(evaluation_only=True)
    official_sanitizer_inputs = [
        (f"official/{test_id}", text) for test_id, text in inputs
    ]
    sanitizer = executor.run(source, official_sanitizer_inputs, sanitizer=True)
    sanitizer_by_id = {item.test_id: item for item in sanitizer.observations}
    eligible_official = []
    exclusion_types = Counter()
    exclusions = []
    if sanitizer.compile_success:
        for test_id, _ in inputs:
            observation = sanitizer_by_id[f"official/{test_id}"]
            failure = sanitizer_failure_type(observation)
            if failure is None:
                eligible_official.append(test_id)
            else:
                exclusion_types[failure] += 1
                exclusions.append(
                    {
                        "exit_code": observation.exit_code,
                        "failure_type": failure,
                        "stderr_hash": observation.stderr_hash,
                        "stderr_length": observation.stderr_length,
                        "test_id": test_id,
                    }
                )
    else:
        exclusion_types["reference_sanitizer_compile_failure"] = len(inputs)
    accepted = []
    assessed_candidate_count = 0
    normal_compile_success = True
    elapsed = sanitizer.total_time_ms
    if sanitizer.compile_success:
        for start in range(0, len(candidates), execution_chunk_size):
            chunk = candidates[start : start + execution_chunk_size]
            chunk_inputs = [
                (f"candidate/{start + index:06d}", item.input_text)
                for index, item in enumerate(chunk)
            ]
            normal_first = executor.run(source, chunk_inputs, sanitizer=False)
            normal_second = executor.run(source, chunk_inputs, sanitizer=False)
            candidate_sanitizer = executor.run(source, chunk_inputs, sanitizer=True)
            elapsed += (
                normal_first.total_time_ms
                + normal_second.total_time_ms
                + candidate_sanitizer.total_time_ms
            )
            assessed_candidate_count += len(chunk)
            normal_compile_success = normal_compile_success and (
                normal_first.compile_success and normal_second.compile_success
            )
            accepted.extend(
                accept_reference_candidates(
                    chunk,
                    normal_first,
                    normal_second,
                    candidate_sanitizer,
                    acceptance_cap=acceptance_cap - len(accepted),
                    start_index=start,
                )
            )
            if len(accepted) >= acceptance_cap:
                break
    execution_counts = {
        "reference_normal": assessed_candidate_count * 2,
        "reference_sanitizer": len(inputs) + assessed_candidate_count,
    }
    return {
        "accepted": accepted,
        "accepted_count": len(accepted),
        "case_id": case.case_id,
        "execution_counts": execution_counts,
        "generator_version": "phase9-deterministic-numeric-mutation-v1",
        "official_test_count": len(inputs),
        "proposal_count": len(candidates),
        "reference_normal_compile_success": normal_compile_success,
        "reference_sanitizer_compile_success": sanitizer.compile_success,
        "sanitizer_eligible_official_test_ids": eligible_official,
        "sanitizer_exclusion_counts": dict(sorted(exclusion_types.items())),
        "sanitizer_exclusions": exclusions,
        "seed": seed,
        "time_ms": elapsed,
    }


def differential_manifest(reference_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    for record in sorted(reference_records, key=lambda item: item["case_id"]):
        accepted = []
        for index, item in enumerate(record["accepted"]):
            accepted.append(
                {
                    "generator_order_hash": item["generator_order_hash"],
                    "input_hash": item["input_hash"],
                    "mutation_value": item["mutation_value"],
                    "reference_determinism_check": "passed",
                    "reference_output_hash": item["reference_output_hash"],
                    "reference_sanitizer_status": item["reference_sanitizer_status"],
                    "source_test_id": item["source_test_id"],
                    "test_id": f"phase9_differential_{index:04d}",
                    "token_index": item["token_index"],
                }
            )
        cases.append(
            {
                "accepted_count": len(accepted),
                "accepted_tests": accepted,
                "case_id": record["case_id"],
                "generator_version": record["generator_version"],
                "proposal_count": record["proposal_count"],
                "seed": record["seed"],
            }
        )
    value: dict[str, Any] = {
        "accepted_test_count": sum(item["accepted_count"] for item in cases),
        "case_count": len(cases),
        "cases": cases,
        "protocol_version": "phase9-differential-tests-v1",
        "proposal_count": sum(item["proposal_count"] for item in cases),
        "zero_accepted_case_count": sum(item["accepted_count"] == 0 for item in cases),
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def _failure_summary(
    observation: BatchObservation, failure_type: str
) -> dict[str, Any]:
    return {
        "actual_output_hash": observation.stdout_hash,
        "exit_code": observation.exit_code,
        "failure_type": failure_type,
        "stderr_excerpt": observation.stderr_excerpt,
        "stderr_hash": observation.stderr_hash,
        "stderr_length": observation.stderr_length,
        "test_id": observation.test_id,
        "timed_out": observation.timed_out,
    }


def validate_patch(
    *,
    entry: dict[str, Any],
    source: str,
    case: BenchmarkCase,
    reference_record: dict[str, Any],
    executor: DockerBatchExecutor,
) -> dict[str, Any]:
    if not entry["hidden_validation_pass"]:
        return {
            "case_id": entry["case_id"],
            "patch_id": entry["patch_id"],
            "strongly_validated": False,
            "V3": "N/A",
            "V4": "N/A",
        }
    official = dict(official_inputs(case))
    sanitizer_ids = reference_record["sanitizer_eligible_official_test_ids"]
    sanitizer_findings = []
    sanitizer_result = None
    if sanitizer_ids:
        sanitizer_result = executor.run(
            source,
            [(test_id, official[test_id]) for test_id in sanitizer_ids],
            sanitizer=True,
        )
        if not sanitizer_result.compile_success:
            sanitizer_findings.append(
                {
                    "failure_type": "sanitizer_compile_failure",
                    "stderr_excerpt": sanitizer_result.compile_stderr_excerpt,
                    "stderr_hash": sanitizer_result.compile_stderr_hash,
                    "stderr_length": sanitizer_result.compile_stderr_length,
                    "test_id": "compile",
                }
            )
        else:
            for observation in sanitizer_result.observations:
                failure = sanitizer_failure_type(observation)
                if failure:
                    sanitizer_findings.append(_failure_summary(observation, failure))
    v3 = "N/A" if not sanitizer_ids else ("FAIL" if sanitizer_findings else "PASS")

    accepted = reference_record["accepted"]
    differential_findings = []
    differential_result = None
    if accepted:
        differential_result = executor.run(
            source,
            [
                (f"phase9_differential_{index:04d}", item["input_text"])
                for index, item in enumerate(accepted)
            ],
            sanitizer=False,
        )
        if not differential_result.compile_success:
            differential_findings.append(
                {
                    "failure_type": "differential_compile_failure",
                    "stderr_excerpt": differential_result.compile_stderr_excerpt,
                    "stderr_hash": differential_result.compile_stderr_hash,
                    "stderr_length": differential_result.compile_stderr_length,
                    "test_id": "compile",
                }
            )
        else:
            for index, observation in enumerate(differential_result.observations):
                expected = accepted[index]["reference_output_hash"]
                failure = differential_failure_type(observation, expected)
                if failure:
                    value = _failure_summary(observation, failure)
                    value["expected_output_hash"] = expected
                    differential_findings.append(value)
    v4 = "N/A" if not accepted else ("FAIL" if differential_findings else "PASS")
    primary = None
    priorities = (
        "ASan",
        "UBSan",
        "sanitizer_timeout",
        "sanitizer_abnormal_exit",
        "sanitizer_compile_failure",
        "differential_output_mismatch",
        "differential_runtime_error",
        "differential_timeout",
        "differential_compile_failure",
    )
    all_findings = [*sanitizer_findings, *differential_findings]
    for failure_type in priorities:
        if any(item["failure_type"] == failure_type for item in all_findings):
            primary = failure_type
            break
    return {
        "case_id": entry["case_id"],
        "differential_findings": differential_findings,
        "execution_counts": {
            "differential": len(accepted) if differential_result else 0,
            "sanitizer": len(sanitizer_ids) if sanitizer_result else 0,
        },
        "patch_id": entry["patch_id"],
        "primary_failure": primary,
        "sanitizer_findings": sanitizer_findings,
        "strongly_validated": v3 == "PASS" and v4 == "PASS",
        "time_ms": sum(
            result.total_time_ms
            for result in (sanitizer_result, differential_result)
            if result is not None
        ),
        "V3": v3,
        "V4": v4,
    }
