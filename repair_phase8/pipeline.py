"""Initial and paired second-round Phase 8 repair attempts."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from benchmark.models import BenchmarkCase
from repair.extraction import extract_source
from repair.models import ModelResponse, PatchEvaluation
from repair.provider import ModelError, RepairModel

from .artifacts import Phase8ArtifactStore, phase8_cache_key
from .context import failed_execution_feedback
from .evaluation import second_round_eligibility
from .models import Phase8Arm, Phase8Prompt
from .prompting import render_second_prompt


Evaluator = Callable[[BenchmarkCase, str], PatchEvaluation]


def _prompt_record(prompt: Phase8Prompt) -> dict[str, object]:
    return {
        "hash": prompt.prompt_hash,
        "oracle_render_hash": prompt.oracle_render_hash,
        "raw_observation_hash": prompt.raw_observation_hash,
        "render_protocol_version": prompt.render_protocol_version,
        "rendered_evidence_hash": prompt.rendered_evidence_hash,
        "system": prompt.system,
        "template_version": prompt.template_version,
        "user": prompt.user,
    }


def _response_record(response: ModelResponse) -> dict[str, object]:
    return {
        "finish_reason": response.finish_reason,
        "id": response.response_id,
        "raw": response.text,
        "response_hash": hashlib.sha256(response.text.encode()).hexdigest(),
    }


def _repair_time_view(case: BenchmarkCase, evaluation: PatchEvaluation) -> dict[str, Any]:
    base_ids = set(case.metadata["phase8"]["base_test_ids"])
    return {
        "base_tests": [
            asdict(item) for item in evaluation.repair_tests if item.test_id in base_ids
        ],
        "compile_exit_code": evaluation.compile_exit_code,
        "compile_stderr": evaluation.compile_stderr,
        "compile_success": evaluation.compile_success,
        "feedback_tests": [
            asdict(item) for item in evaluation.repair_tests if item.test_id not in base_ids
        ],
        "success": evaluation.plausible,
    }


def _persist_model_error(
    store: Phase8ArtifactStore,
    arm: Phase8Arm,
    case: BenchmarkCase,
    key: str,
    record: dict[str, Any],
    exc: ModelError,
) -> dict[str, Any]:
    record.update(
        {
            "classification": "provider_failure",
            "completed": True,
            "error": f"{type(exc).__name__}: {exc}",
            "second_round_eligible": False,
        }
    )
    return store.write(arm, case.case_id, key, record)


def run_initial_attempt(
    case: BenchmarkCase,
    prompt: Phase8Prompt,
    model: RepairModel,
    evaluator: Evaluator,
    store: Phase8ArtifactStore,
    partition_hash: str,
    *,
    raw_runtime_manifest_hash: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    key = phase8_cache_key(
        case.case_id, Phase8Arm.INITIAL, prompt, model.parameters, partition_hash
    )
    if resume:
        cached = store.load(Phase8Arm.INITIAL, case.case_id, key)
        if cached is not None and cached.get("completed") is True:
            return cached
    record: dict[str, Any] = {
        "arm": Phase8Arm.INITIAL.value,
        "attempt": 1,
        "cache_key": key,
        "case_id": case.case_id,
        "completed": False,
        "model_parameters": model.parameters.cache_view(),
        "prompt": _prompt_record(prompt),
        "protocol_version": "phase8-v1",
        "oracle_render_hash": prompt.oracle_render_hash,
        "raw_runtime_observation_hash": prompt.raw_observation_hash,
        "raw_runtime_manifest_hash": raw_runtime_manifest_hash,
        "render_protocol_version": prompt.render_protocol_version,
        "rendered_evidence_hash": prompt.rendered_evidence_hash,
        "test_partition_hash": partition_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = model.generate(prompt)
    except ModelError as exc:
        return _persist_model_error(
            store, Phase8Arm.INITIAL, case, key, record, exc
        )
    extraction = extract_source(response.text)
    record["model_response"] = _response_record(response)
    record["extraction"] = asdict(extraction)
    if extraction.source is None:
        decision = second_round_eligibility(
            case, None, invalid_model_output=True
        )
        record.update(
            {
                "classification": "invalid_model_output",
                "completed": True,
                "eligibility_reason": decision.reason,
                "second_round_eligible": False,
            }
        )
        return store.write(Phase8Arm.INITIAL, case.case_id, key, record)
    evaluation = evaluator(case, extraction.source)
    decision = second_round_eligibility(case, evaluation)
    record.update(
        {
            "classification": evaluation.classification.value,
            "completed": True,
            "eligibility_reason": decision.reason,
            "evaluation": evaluation.to_dict(),
            "failure_evidence": (
                failed_execution_feedback(case, evaluation)
                if decision.eligible
                else None
            ),
            "failure_evidence_hash": None,
            "first_patch_hash": hashlib.sha256(extraction.source.encode()).hexdigest(),
            "hidden_validation_results": [
                asdict(item) for item in evaluation.validation_tests
            ],
            "repair_time_results": _repair_time_view(case, evaluation),
            "second_round_eligible": decision.eligible,
        }
    )
    if record["failure_evidence"] is not None:
        record["failure_evidence_hash"] = hashlib.sha256(
            json.dumps(
                record["failure_evidence"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    return store.write(Phase8Arm.INITIAL, case.case_id, key, record)


def run_second_attempt(
    case: BenchmarkCase,
    initial_prompt: Phase8Prompt,
    initial_record: dict[str, Any],
    arm: Phase8Arm,
    model: RepairModel,
    evaluator: Evaluator,
    store: Phase8ArtifactStore,
    partition_hash: str,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    if not initial_record.get("second_round_eligible"):
        raise ValueError("case is not eligible for a second-round attempt")
    previous_patch = initial_record["extraction"]["source"]
    feedback = initial_record["failure_evidence"] if arm is Phase8Arm.FEEDBACK else None
    prompt = render_second_prompt(initial_prompt, previous_patch, arm, feedback)
    first_hash = initial_record["first_patch_hash"]
    key = phase8_cache_key(
        case.case_id,
        arm,
        prompt,
        model.parameters,
        partition_hash,
        first_hash,
    )
    if resume:
        cached = store.load(arm, case.case_id, key)
        if cached is not None and cached.get("completed") is True:
            return cached
    record: dict[str, Any] = {
        "arm": arm.value,
        "attempt": 2,
        "cache_key": key,
        "case_id": case.case_id,
        "completed": False,
        "failure_evidence_hash": (
            initial_record["failure_evidence_hash"]
            if arm is Phase8Arm.FEEDBACK
            else None
        ),
        "first_patch_hash": first_hash,
        "initial_prompt_hash": initial_prompt.prompt_hash,
        "model_parameters": model.parameters.cache_view(),
        "prompt": _prompt_record(prompt),
        "protocol_version": "phase8-v1",
        "raw_runtime_manifest_hash": initial_record.get("raw_runtime_manifest_hash"),
        "raw_first_patch_observation_hash": (
            prompt.raw_observation_hash if arm is Phase8Arm.FEEDBACK else None
        ),
        "render_protocol_version": prompt.render_protocol_version,
        "rendered_evidence_hash": (
            prompt.rendered_evidence_hash if arm is Phase8Arm.FEEDBACK else None
        ),
        "second_round_arm": arm.value,
        "test_partition_hash": partition_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = model.generate(prompt)
    except ModelError as exc:
        return _persist_model_error(store, arm, case, key, record, exc)
    extraction = extract_source(response.text)
    record["model_response"] = _response_record(response)
    record["extraction"] = asdict(extraction)
    if extraction.source is None:
        record.update({"classification": "invalid_model_output", "completed": True})
        return store.write(arm, case.case_id, key, record)
    evaluation = evaluator(case, extraction.source)
    record.update(
        {
            "classification": evaluation.classification.value,
            "completed": True,
            "evaluation": evaluation.to_dict(),
            "hidden_validation_results": [
                asdict(item) for item in evaluation.validation_tests
            ],
            "repair_time_results": _repair_time_view(case, evaluation),
            "second_patch_hash": hashlib.sha256(extraction.source.encode()).hexdigest(),
        }
    )
    return store.write(arm, case.case_id, key, record)


def attach_provider_metadata(
    store: Phase8ArtifactStore,
    record: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if metadata is None:
        return record
    updated = dict(record)
    updated["provider_response_metadata"] = metadata
    return store.write(
        Phase8Arm(updated["arm"]),
        updated["case_id"],
        updated["cache_key"],
        updated,
    )
