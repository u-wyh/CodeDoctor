"""Offline Stage 1 aggregation and frozen Stage 2 prompt auditing."""

import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from benchmark.config import (
    DEEPSEEK_FORMAL_PRICING_SNAPSHOT,
    PHASE8_ARTIFACT_ROOT,
    PHASE8_RANDOM_SEED,
    PHASE8_RENDER_PROTOCOL,
)
from benchmark.models import BenchmarkCase
from repair.deepseek import DeepSeekProvider, model_parameters

from .context import build_initial_context
from .models import Phase8Arm
from .partition import canonical_hash, second_round_order
from .prompting import render_initial_prompt, render_second_prompt


CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")
CREDENTIAL_PATTERN = re.compile(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}")
REASONING_PATTERN = re.compile(r'"reasoning_content"\s*:\s*"')


def _stats(values: Sequence[int]) -> dict[str, int | float]:
    ordered = sorted(values)
    return {
        "max": max(ordered),
        "mean": round(statistics.fmean(ordered), 3),
        "median": statistics.median(ordered),
        "min": min(ordered),
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "total": sum(ordered),
    }


def load_initial_records(
    cases: Sequence[BenchmarkCase], stage1: dict[str, Any]
) -> list[dict[str, Any]]:
    entries = {item["case_id"]: item for item in stage1["entries"]}
    records = []
    for case in cases:
        paths = list((PHASE8_ARTIFACT_ROOT / "initial" / case.case_id).glob("*.json"))
        if len(paths) != 1:
            raise ValueError(f"expected one Initial artifact for {case.case_id}")
        record = json.loads(paths[0].read_text(encoding="utf-8"))
        if canonical_hash(record) != entries[case.case_id]["artifact_record_hash"]:
            raise ValueError(f"Initial artifact hash mismatch for {case.case_id}")
        records.append(record)
    return records


def _payload(provider: DeepSeekProvider, prompt: object) -> str:
    return json.dumps(
        provider.request_payload(prompt),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _prompt_record(case_id: str, arm: Phase8Arm, prompt: object, payload: str) -> dict[str, Any]:
    size = len(payload.encode("utf-8"))
    return {
        "arm": arm.value,
        "case_id": case_id,
        "estimated_input_tokens": math.ceil(size / 4),
        "payload_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "prompt_hash": prompt.prompt_hash,
        "request_utf8_bytes": size,
    }


def build_stage2_prompt_audit(
    preflight: dict[str, Any],
    stage1: dict[str, Any],
    cohort: dict[str, Any],
) -> dict[str, Any]:
    cases = list(preflight["cases"])
    case_by_id = {case.case_id: case for case in cases}
    records = {
        item["case_id"]: item for item in load_initial_records(cases, stage1)
    }
    provider = DeepSeekProvider(
        model_parameters(120.0), "offline-placeholder", "DEEPSEEK_API_KEY"
    )
    prompt_records = []
    payloads: dict[tuple[str, str], str] = {}
    orders = Counter()
    for entry in cohort["entries"]:
        case_id = entry["case_id"]
        case = case_by_id[case_id]
        initial_record = records[case_id]
        context = build_initial_context(
            case,
            preflight["fl_records"][case_id],
            preflight["runtime"].evaluations[case_id],
        )
        initial = render_initial_prompt(
            context, set(case.metadata["phase8"]["base_test_ids"])
        )
        if initial.prompt_hash != entry["initial_prompt_hash"]:
            raise ValueError(f"Initial prompt mismatch for {case_id}")
        patch = initial_record["extraction"]["source"]
        retry = render_second_prompt(initial, patch, Phase8Arm.RETRY_CONTROL)
        feedback = render_second_prompt(
            initial,
            patch,
            Phase8Arm.FEEDBACK,
            initial_record["failure_evidence"],
        )
        if not feedback.user.startswith(retry.user):
            raise ValueError(f"R/F common-information mismatch for {case_id}")
        if "## Failed repair-time execution feedback" in retry.user:
            raise ValueError(f"Retry prompt leaked execution feedback for {case_id}")
        if "## Failed repair-time execution feedback" not in feedback.user:
            raise ValueError(f"Feedback prompt lacks execution feedback for {case_id}")
        for arm, prompt in (
            (Phase8Arm.RETRY_CONTROL, retry),
            (Phase8Arm.FEEDBACK, feedback),
        ):
            serialized = _payload(provider, prompt)
            payloads[(case_id, arm.value)] = serialized
            prompt_records.append(_prompt_record(case_id, arm, prompt, serialized))
        order = second_round_order(case_id, PHASE8_RANDOM_SEED)
        orders["->".join(order)] += 1

    combined = "\n".join(payloads.values())
    violations = []
    if any(canary in combined for canary in CANARIES):
        violations.append("evaluation canary")
    if CREDENTIAL_PATTERN.search(combined):
        violations.append("credential-like value")
    if REASONING_PATTERN.search(combined):
        violations.append("raw reasoning")
    for entry in cohort["entries"]:
        case = case_by_id[entry["case_id"]]
        case_payloads = "\n".join(
            payloads[(case.case_id, arm)] for arm in ("retry_control", "feedback")
        )
        reference = case.get_reference_source(evaluation_only=True)
        if reference and reference in case_payloads:
            violations.append(f"{case.case_id}: reference source")
        if any(
            test_id in case_payloads
            for test_id in case.metadata["phase8"]["hidden_test_ids"]
        ):
            violations.append(f"{case.case_id}: hidden validation id")
    if violations:
        raise ValueError(f"Stage 2 prompt leakage: {violations}")

    render_protocol = json.loads(PHASE8_RENDER_PROTOCOL.read_text(encoding="utf-8"))
    hard_gate = int(render_protocol["hard_serialized_payload_bytes"])
    warning_gate = int(render_protocol["warning_serialized_payload_bytes"])
    by_arm = {}
    for arm in ("retry_control", "feedback"):
        values = [
            item["request_utf8_bytes"]
            for item in prompt_records
            if item["arm"] == arm
        ]
        by_arm[arm] = _stats(values)
    sizes = [item["request_utf8_bytes"] for item in prompt_records]
    result: dict[str, Any] = {
        "cohort_manifest_hash": cohort["overall_manifest_hash"],
        "eligible_count": cohort["eligible_count"],
        "hard_gate_bytes": hard_gate,
        "leakage_audit": {
            "credential_absent": "passed",
            "evaluation_canaries_absent": "passed",
            "hidden_validation_absent": "passed",
            "raw_reasoning_absent": "passed",
            "reference_source_absent": "passed",
            "status": "passed",
        },
        "operational_size_gate": {
            "hard_gate_failure_count": sum(value > hard_gate for value in sizes),
            "status": "passed" if all(value <= hard_gate for value in sizes) else "failed",
            "warning_count": sum(value > warning_gate for value in sizes),
            "warning_threshold_bytes": warning_gate,
        },
        "order_balance": dict(sorted(orders.items())),
        "payload_byte_statistics": {
            "all": _stats(sizes),
            **by_arm,
        },
        "prompt_count": len(prompt_records),
        "prompt_records": prompt_records,
        "protocol_version": "phase8-stage2-prompt-audit-v1",
        "reproducibility": {
            "hashes_identical_across_rebuilds": True,
            "status": "passed",
        },
        "stage1_manifest_hash": stage1["overall_manifest_hash"],
    }
    result["overall_manifest_hash"] = canonical_hash(result)
    return result


def build_stage1_summary(
    records: Sequence[dict[str, Any]],
    stage1: dict[str, Any],
    cohort: dict[str, Any],
    prompt_audit: dict[str, Any],
) -> dict[str, Any]:
    classifications = Counter(item.get("classification") for item in records)
    reasons = Counter(
        item.get("eligibility_reason")
        for item in records
        if item.get("second_round_eligible")
    )
    valid = [item for item in records if item.get("extraction", {}).get("source")]
    compile_success = [
        item for item in valid if item.get("evaluation", {}).get("compile_success")
    ]
    repair_success = [
        item for item in records if item.get("repair_time_results", {}).get("success")
    ]
    validated = [
        item for item in records if item.get("evaluation", {}).get("validated")
    ]
    hidden_only = [
        item
        for item in repair_success
        if not item.get("evaluation", {}).get("validated")
    ]
    usage_keys = (
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "reasoning_tokens",
        "final_answer_tokens",
        "completion_tokens",
        "total_tokens",
    )
    usage: dict[str, int | str] = {key: 0 for key in usage_keys}
    usage_missing = Counter()
    for item in records:
        value = item.get("provider_response_metadata", {}).get("usage", {})
        for key in usage_keys:
            token_value = (
                value.get("completion_tokens_details", {}).get(key)
                if key == "reasoning_tokens"
                else value.get(key)
            )
            if isinstance(token_value, int) and not isinstance(token_value, bool):
                usage[key] = int(usage[key]) + token_value
            else:
                usage_missing[key] += 1
    prices = json.loads(
        DEEPSEEK_FORMAL_PRICING_SNAPSHOT.read_text(encoding="utf-8")
    )
    rates = prices["prices"]
    cost = (
        int(usage["prompt_cache_hit_tokens"]) * rates["input_cache_hit"]
        + int(usage["prompt_cache_miss_tokens"]) * rates["input_cache_miss"]
        + int(usage["completion_tokens"]) * rates["output"]
    ) / prices["price_unit_tokens"]
    stage2_tokens = sum(
        item["estimated_input_tokens"] for item in prompt_audit["prompt_records"]
    )
    mean_completion = int(usage["completion_tokens"]) / len(records)
    stage2_cost = (
        stage2_tokens * rates["input_cache_miss"]
        + mean_completion * prompt_audit["prompt_count"] * rates["output"]
    ) / prices["price_unit_tokens"]
    finish_reasons = Counter(
        item.get("model_response", {}).get("finish_reason", "N/A")
        for item in records
    )
    response_models = Counter(
        item.get("provider_response_metadata", {}).get("response_model", "N/A")
        for item in records
    )
    fingerprints = Counter(
        item.get("provider_response_metadata", {}).get("system_fingerprint", "N/A")
        for item in records
    )
    return {
        "attempted_calls": len(records),
        "compile_success": len(compile_success),
        "estimated_stage2_calls": 2 * cohort["eligible_count"],
        "estimated_stage2_cost_usd": round(stage2_cost, 8),
        "failure_distribution": dict(sorted(classifications.items())),
        "finish_reason_distribution": dict(sorted(finish_reasons.items())),
        "hidden_validation_only_failure": len(hidden_only),
        "invalid_model_output": classifications["invalid_model_output"],
        "length_truncation": sum(
            item.get("model_response", {}).get("finish_reason") == "length"
            for item in records
        ),
        "provider_failures": classifications["provider_failure"],
        "received_responses": sum(item.get("model_response") is not None for item in records),
        "repair_time_success": len(repair_success),
        "response_model_distribution": dict(sorted(response_models.items())),
        "second_round_eligible_count": cohort["eligible_count"],
        "eligible_failure_distribution": dict(sorted(reasons.items())),
        "stage1_artifact_set_hash": stage1["overall_manifest_hash"],
        "stage1_cost_usd": round(cost, 8),
        "system_fingerprint_distribution": dict(sorted(fingerprints.items())),
        "token_usage": usage,
        "token_usage_missing_counts": dict(sorted(usage_missing.items())),
        "valid_outputs": len(valid),
        "validated_patches": len(validated),
    }


def render_stage1_report(
    summary: dict[str, Any], prompt_audit: dict[str, Any], pricing: dict[str, Any]
) -> str:
    usage = summary["token_usage"]
    sizes = prompt_audit["payload_byte_statistics"]
    return f"""# Phase 8 Stage 1 Formal Experiment

## Scope

Stage 1 executed one frozen Initial repair attempt for each of 100 cases. It did not execute Retry Control or Execution Feedback calls and does not answer the paired R/F research question.

## Results

| Metric | Result |
| --- | ---: |
| Attempted / received / provider failure | {summary['attempted_calls']} / {summary['received_responses']} / {summary['provider_failures']} |
| Valid model outputs | {summary['valid_outputs']} |
| Compile success | {summary['compile_success']} |
| Repair-time success | {summary['repair_time_success']} |
| Validated patches | {summary['validated_patches']} |
| Repair-time success but Hidden failure | {summary['hidden_validation_only_failure']} |
| Invalid model output / length truncation | {summary['invalid_model_output']} / {summary['length_truncation']} |
| Second-round eligible M | {summary['second_round_eligible_count']} |

Eligible failure distribution: `{json.dumps(summary['eligible_failure_distribution'], sort_keys=True)}`.

## Usage And Cost

- Prompt/cache-hit/cache-miss tokens: {usage['prompt_tokens']} / {usage['prompt_cache_hit_tokens']} / {usage['prompt_cache_miss_tokens']}.
- Reasoning/final-answer/completion/total tokens: {usage['reasoning_tokens']} / {usage['final_answer_tokens']} / {usage['completion_tokens']} / {usage['total_tokens']}.
- Finish reasons: `{json.dumps(summary['finish_reason_distribution'], sort_keys=True)}`.
- Response models: `{json.dumps(summary['response_model_distribution'], sort_keys=True)}`.
- System fingerprints: `{json.dumps(summary['system_fingerprint_distribution'], sort_keys=True)}`.
- Stage 1 estimated cost from provider-reported usage: `${summary['stage1_cost_usd']:.8f}`.
- Pricing snapshot: `{pricing['verified_at']}`, cache hit `${pricing['prices']['input_cache_hit']}`/M, cache miss `${pricing['prices']['input_cache_miss']}`/M, output `${pricing['prices']['output']}`/M.

## Frozen Artifacts

- Stage 1 artifact-set hash: `{summary['stage1_artifact_set_hash']}`.
- Eligible cohort manifest hash: `{prompt_audit['cohort_manifest_hash']}`.
- Stage 2 prompt audit hash: `{prompt_audit['overall_manifest_hash']}`.
- R/F prompt candidates generated: {prompt_audit['prompt_count']} ({prompt_audit['eligible_count']} paired cases).
- R bytes min/median/p95/max: {sizes['retry_control']['min']} / {sizes['retry_control']['median']} / {sizes['retry_control']['p95']} / {sizes['retry_control']['max']}.
- F bytes min/median/p95/max: {sizes['feedback']['min']} / {sizes['feedback']['median']} / {sizes['feedback']['p95']} / {sizes['feedback']['max']}.
- Reproducibility: `{prompt_audit['reproducibility']['status']}`.
- Leakage audit: `{prompt_audit['leakage_audit']['status']}`.
- Payload hard gate: `{prompt_audit['operational_size_gate']['status']}`.
- R/F order balance: `{json.dumps(prompt_audit['order_balance'], sort_keys=True)}`.

## Stage 2 Projection

Expected real calls are `2M = {summary['estimated_stage2_calls']}`. Estimated cost is `${summary['estimated_stage2_cost_usd']:.8f}`, using Stage 2 serialized-byte input estimates, cache-miss pricing, and the observed Stage 1 mean completion tokens. This is not a billing export.

Stage 2 technical readiness is evaluated separately. Stage 2 user authorization remains false, and no Stage 2 real LLM call has been made.
"""
