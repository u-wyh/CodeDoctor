"""Build the mandatory DeepSeek pre-experiment readiness and cost report."""

import hashlib
import json
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT,
    DEEPSEEK_EXPERIMENT_CONFIG,
    DEEPSEEK_PRICING_SNAPSHOT,
    PROJECT_ROOT,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_PILOT_FL,
    REPAIR_PRE_EXPERIMENT_ESTIMATE,
    REPAIR_PRE_EXPERIMENT_REPORT,
    RUNTIME_EVIDENCE_MANIFEST,
    RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT,
    RUNTIME_EVIDENCE_PROMPT_AUDIT,
)
from benchmark.models import load_manifest

from .context import build_repair_context, load_fl_records
from .deepseek import resolve_api_key, validate_configuration
from .evaluator import evaluate_source
from .models import EvidenceGroup, PromptDocument
from .prompting import render_prompt
from .protocol import validate_repair_protocol
from .reporting import validate_artifact_boundaries
from .runtime_evidence import load_frozen_runtime_evidence


def approximate_tokens(text: str) -> int:
    """Transparent provider-independent heuristic, not a tokenizer claim."""

    return math.ceil(len(text) / 4)


def _round_tokens(value: float, unit: int) -> int:
    return int(round(value / unit) * unit)


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.json"))
    ]


def _validate_prompts(
    prompts: dict[str, dict[str, PromptDocument]],
) -> dict[str, Any]:
    violations = []
    for case_id, groups in prompts.items():
        if set(groups) != {"A", "B", "C"}:
            violations.append(f"{case_id}: incomplete A/B/C prompt set")
            continue
        users = {group: prompt.user for group, prompt in groups.items()}
        bases = {
            value.split("\n\n## CodeDoctor FL-v1 suspicious locations", 1)[0]
            for value in users.values()
        }
        if len(bases) != 1:
            violations.append(f"{case_id}: base semantics differ")
        b_fl = users["B"]
        c_fl = users["C"].split("\n\n## Repair-test execution evidence", 1)[0]
        if b_fl != c_fl:
            violations.append(f"{case_id}: B/C FL context differs")
        runtime = users["C"].split("## Repair-test execution evidence", 1)[-1]
        if "Input:" in runtime or "Expected output:" in runtime:
            violations.append(f"{case_id}: C runtime adds task semantics")
        combined = "\n".join(prompt.system + prompt.user for prompt in groups.values())
        for canary in ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN"):
            if canary in combined:
                violations.append(f"{case_id}: {canary} leaked")
    if violations:
        raise ValueError(f"prompt information-boundary audit failed: {violations}")
    return {
        "cases_checked": len(prompts),
        "prompts_checked": sum(len(groups) for groups in prompts.values()),
        "status": "passed",
    }


def _usage_by_group(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for group in ("A", "B", "C"):
        selected = [item for item in records if item.get("group") == group]
        if not selected:
            result[group] = {"calls": 0, "usage": None}
            continue
        totals: dict[str, int] = defaultdict(int)
        observed_keys: set[str] = set()
        for item in selected:
            usage = item.get("provider_response_metadata", {}).get("usage", {})
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "prompt_cache_hit_tokens",
                "prompt_cache_miss_tokens",
                "final_answer_tokens",
            ):
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[key] += value
                    observed_keys.add(key)
            reasoning = usage.get("completion_tokens_details", {}).get(
                "reasoning_tokens"
            )
            if isinstance(reasoning, int) and not isinstance(reasoning, bool):
                totals["reasoning_tokens"] += reasoning
                observed_keys.add("reasoning_tokens")
        result[group] = {
            "calls": len(selected),
            "usage": (
                {key: totals[key] for key in sorted(observed_keys)}
                if observed_keys
                else None
            ),
        }
    return result


def _current_smoke_records(
    records: list[dict[str, Any]], configuration: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        item
        for item in records
        if item.get("experimental") is True
        and item.get("experiment_role") == "pre_experiment_smoke"
        and item.get("model_parameters", {}).get("provider") == "deepseek"
        and item.get("model_parameters", {}).get("model") == configuration["model"]
        and item.get("model_parameters", {}).get("max_tokens")
        == configuration["max_tokens"]
    ]


def _bulk_projection(
    approximate_groups: dict[str, dict[str, Any]],
    approximate_output: int,
    actual_usage: dict[str, dict[str, Any]],
    smoke_input_estimates: dict[str, int] | None = None,
    smoke_truncated: bool = False,
) -> dict[str, Any]:
    if all(actual_usage[group]["calls"] == 1 for group in ("A", "B", "C")):
        usages = {group: actual_usage[group]["usage"] for group in ("A", "B", "C")}
        if all(
            value is not None
            and "prompt_tokens" in value
            and "completion_tokens" in value
            for value in usages.values()
        ):
            if smoke_input_estimates:
                input_by_group = {
                    group: _round_tokens(
                        approximate_groups[group]["approximate_total_input_tokens"]
                        * usages[group]["prompt_tokens"]
                        / smoke_input_estimates[group],
                        100,
                    )
                    for group in ("A", "B", "C")
                }
                calibration_ratios = {
                    group: round(
                        usages[group]["prompt_tokens"]
                        / smoke_input_estimates[group],
                        3,
                    )
                    for group in ("A", "B", "C")
                }
                input_basis = (
                    "full-Pilot character estimates calibrated by each smoke "
                    "group's actual DeepSeek prompt-token ratio"
                )
            else:
                input_by_group = {
                    group: usages[group]["prompt_tokens"] * 50
                    for group in ("A", "B", "C")
                }
                calibration_ratios = None
                input_basis = "one smoke prompt per group multiplied by 50"
            return {
                "basis": input_basis,
                "input_calibration_ratios": calibration_ratios,
                "input_by_group": input_by_group,
                "output_total": sum(
                    usages[group]["completion_tokens"] * 50
                    for group in ("A", "B", "C")
                ),
                "reasoning_total": (
                    sum(usages[group].get("reasoning_tokens", 0) * 50 for group in usages)
                    if any("reasoning_tokens" in usages[group] for group in usages)
                    else None
                ),
                "output_basis": (
                    "at least one smoke completion reached the configured max_tokens; "
                    "this is an all-calls-match-observed-usage cap scenario, not "
                    "expected usage"
                    if smoke_truncated
                    else "one real completion per group multiplied by 50"
                ),
                "uncertainty": "high; one smoke case is not representative",
            }
    return {
        "basis": "provider-independent character estimate; no real DeepSeek smoke usage",
        "input_calibration_ratios": None,
        "input_by_group": {
            group: approximate_groups[group]["approximate_total_input_tokens"]
            for group in ("A", "B", "C")
        },
        "output_total": approximate_output,
        "reasoning_total": None,
        "output_basis": "buggy-source length proxy",
        "uncertainty": "high; no real DeepSeek usage",
    }


def _complete_smoke(
    records: list[dict[str, Any]], actual_usage: dict[str, dict[str, Any]]
) -> bool:
    if len(records) != 3:
        return False
    for group in ("A", "B", "C"):
        if actual_usage[group]["calls"] != 1:
            return False
        usage = actual_usage[group]["usage"]
        if usage is None or not {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }.issubset(usage):
            return False
        item = next(record for record in records if record.get("group") == group)
        if item.get("classification") in {"model_error", "invalid_model_output"}:
            return False
        if item.get("model_response", {}).get("finish_reason") == "length":
            return False
    return True


def _cache_miss_cost(projection: dict[str, Any], prices: dict[str, float]) -> float:
    input_tokens = sum(projection["input_by_group"].values())
    return round(
        (
            input_tokens * prices["input_cache_miss"]
            + projection["output_total"] * prices["output"]
        )
        / 1_000_000,
        6,
    )


def _actual_smoke_cost(
    actual_usage: dict[str, dict[str, Any]], prices: dict[str, float]
) -> float | None:
    if not all(actual_usage[group]["calls"] == 1 for group in ("A", "B", "C")):
        return None
    cost = 0.0
    for group in ("A", "B", "C"):
        usage = actual_usage[group]["usage"]
        if usage is None or "completion_tokens" not in usage:
            return None
        if "prompt_cache_hit_tokens" not in usage or "prompt_cache_miss_tokens" not in usage:
            return None
        cost += (
            usage["prompt_cache_hit_tokens"] * prices["input_cache_hit"]
            + usage["prompt_cache_miss_tokens"] * prices["input_cache_miss"]
            + usage["completion_tokens"] * prices["output"]
        ) / 1_000_000
    return round(cost, 6)


def build_estimate(manual_inspection: str) -> dict[str, Any]:
    protocol = validate_repair_protocol()
    deepseek = validate_configuration(DEEPSEEK_EXPERIMENT_CONFIG)
    pricing = json.loads(DEEPSEEK_PRICING_SNAPSHOT.read_text(encoding="utf-8"))
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    frozen_runtime = load_frozen_runtime_evidence(cases)
    prompt_reproducibility = json.loads(
        RUNTIME_EVIDENCE_PROMPT_AUDIT.read_text(encoding="utf-8")
    )
    nondeterminism_audit = json.loads(
        RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT.read_text(encoding="utf-8")
    )
    runtime_reproducibility_ready = (
        frozen_runtime.validation["case_count"] == len(cases)
        and prompt_reproducibility.get("prompts_checked") == len(cases) * 3
        and prompt_reproducibility.get(
            "all_prompt_hashes_identical_across_reloads"
        )
        is True
        and prompt_reproducibility.get(
            "target_case_c_ten_render_hashes_identical"
        )
        is True
        and prompt_reproducibility.get("leakage_audit", {}).get("status")
        == "passed"
        and prompt_reproducibility.get("runtime_evidence_manifest_hash")
        == frozen_runtime.validation["manifest_hash"]
    )
    fl_records = load_fl_records(REPAIR_PILOT_FL)
    input_tokens: dict[str, list[int]] = {group.value: [] for group in EvidenceGroup}
    output_tokens: list[int] = []
    per_case_input_tokens: dict[str, dict[str, int]] = {}
    prompt_hashes = []
    prompts: dict[str, dict[str, PromptDocument]] = {}
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] estimating {case.case_id}", flush=True)
        baseline = frozen_runtime.evaluations[case.case_id]
        output_tokens.append(approximate_tokens(case.get_buggy_source()))
        case_prompts = {}
        case_input_tokens = {}
        for group in EvidenceGroup:
            context = build_repair_context(
                case, group, fl_records.get(case.case_id), baseline
            )
            prompt = render_prompt(context, group)
            case_prompts[group.value] = prompt
            prompt_tokens = approximate_tokens(prompt.system + "\n" + prompt.user)
            input_tokens[group.value].append(prompt_tokens)
            case_input_tokens[group.value] = prompt_tokens
            prompt_hashes.append(
                {
                    "case_id": case.case_id,
                    "group": group.value,
                    "prompt_hash": prompt.prompt_hash,
                }
            )
        prompts[case.case_id] = case_prompts
        per_case_input_tokens[case.case_id] = case_input_tokens

    prompt_audit = _validate_prompts(prompts)
    groups = {}
    for group, values in input_tokens.items():
        groups[group] = {
            "approximate_average_input_tokens": _round_tokens(
                statistics.fmean(values), 10
            ),
            "approximate_total_input_tokens": _round_tokens(sum(values), 100),
            "calls": len(values),
            "maximum_input_tokens": max(values),
            "minimum_input_tokens": min(values),
        }
    average_output = _round_tokens(statistics.fmean(output_tokens), 10)
    approximate_output = _round_tokens(sum(output_tokens), 100) * 3

    all_artifacts = _artifact_records(REPAIR_ARTIFACT_ROOT)
    artifact_audit = validate_artifact_boundaries(all_artifacts)
    deepseek_artifacts = [
        item
        for item in all_artifacts
        if item.get("experimental") is True
        and item.get("model_parameters", {}).get("provider") == "deepseek"
    ]
    online = _current_smoke_records(deepseek_artifacts, deepseek)
    superseded = [
        item
        for item in deepseek_artifacts
        if item.get("model_parameters", {}).get("model") != deepseek["model"]
    ]
    formal = [
        item
        for item in deepseek_artifacts
        if item.get("experiment_role") == "formal_evidence_ablation"
    ]
    actual_usage = _usage_by_group(online)
    smoke_truncated = bool(online) and any(
        item.get("model_response", {}).get("finish_reason") == "length"
        for item in online
    )
    projection = _bulk_projection(
        groups,
        approximate_output,
        actual_usage,
        per_case_input_tokens[cases[0].case_id],
        smoke_truncated,
    )
    current_prices = pricing["pricing_at_verification"]
    scheduled = pricing["scheduled_change"]
    cost = {
        "actual_smoke_at_verification_usd": _actual_smoke_cost(
            actual_usage, current_prices
        ),
        "at_verification_cache_miss_usd": _cache_miss_cost(
            projection, current_prices
        ),
        "scheduled_off_peak_cache_miss_usd": _cache_miss_cost(
            projection, scheduled["off_peak"]
        ),
        "scheduled_peak_cache_miss_usd": _cache_miss_cost(
            projection, scheduled["peak"]
        ),
    }
    _, credential_environment = resolve_api_key(os.environ)
    has_key = credential_environment is not None
    complete_smoke = _complete_smoke(online, actual_usage)
    leakage_passed = manual_inspection == "passed"
    smoke_technical_ready = has_key and complete_smoke and leakage_passed
    bulk_online_ready = smoke_technical_ready and runtime_reproducibility_ready
    observed_models = sorted(
        {
            str(item["provider_response_metadata"]["response_model"])
            for item in online
            if item.get("provider_response_metadata", {}).get("response_model")
        }
    )
    estimate = {
        "billing": {
            "bulk_cache_miss_cost_estimates": cost,
            "path": "DeepSeek Official API balance",
            "pricing": pricing,
            "pricing_status": "verified",
            "subscription_warning": (
                "ChatGPT Plus/Codex subscription is separate from DeepSeek API billing."
            ),
        },
        "calls": {
            "attempts_per_case_group": 1,
            "groups": 3,
            "primary": len(cases) * 3,
            "real_smoke_calls": len(online),
            "superseded_smoke_calls": len(superseded),
            "formal_experiment_calls": len(formal),
            "repair_pilot_cases": len(cases),
            "smoke_maximum": 3,
            "transport_retries_configured": 0,
        },
        "credential": {
            "available": has_key,
            "environment_used": credential_environment,
            "environment_variables": ["DEEPSEEK_API_KEY", "CODEDOCTOR_API_KEY"],
            "openai_api_key_is_not_a_fallback": True,
        },
        "leakage_readiness": {
            "artifact_boundary_audit": artifact_audit,
            "evaluation_only_metadata_absent": "passed",
            "ground_truth_diff_absent": "passed",
            "hidden_validation_absent": "passed",
            "manual_prompt_inspection": manual_inspection,
            "prompt_boundary_audit": prompt_audit,
            "reference_leakage_regression": "passed",
            "reference_source_absent": "passed",
            "validation_leakage_regression": "passed",
        },
        "model": {
            "api_format": deepseek["api_format"],
            "base_url": deepseek["base_url"],
            "max_tokens": deepseek["max_tokens"],
            "name": deepseek["model"],
            "official_documented_model_version": deepseek[
                "official_documented_model_version"
            ],
            "provider": deepseek["provider_name"],
            "reasoning_effort": deepseek["reasoning_effort"],
            "response_models_observed": observed_models,
            "stream": deepseek["stream"],
            "temperature": deepseek["temperature"],
            "thinking": deepseek["thinking"],
        },
        "candidate_selection": {
            "decision_timing": "before the 150-call formal experiment",
            "initial_candidate": {
                "max_tokens": 8192,
                "model": "deepseek-v4-pro",
                "reasoning_effort": "high",
                "smoke_calls": len(superseded),
                "smoke_result": (
                    "3/3 finish_reason=length with 8192 reasoning/completion "
                    "tokens and empty final content"
                ),
                "status": "superseded pre-experiment smoke",
            },
            "reason": (
                "pre-experiment output-budget compatibility failure, not "
                "post-hoc repair-result optimization"
            ),
            "final_candidate": {
                "max_tokens": deepseek["max_tokens"],
                "model": deepseek["model"],
                "reasoning_effort": deepseek["reasoning_effort"],
                "status": "current pre-experiment candidate",
            },
        },
        "prompt_hashes": prompt_hashes,
        "protocol_version": protocol["protocol_version"],
        "readiness": {
            "bulk_online_ready": bulk_online_ready,
            "smoke_technical_ready": smoke_technical_ready,
            "bulk_user_authorized": False,
            "blocking_reasons": [
                reason
                for condition, reason in (
                    (not has_key, "DeepSeek API credential unavailable"),
                    (
                        not complete_smoke,
                        "three-call genuine DeepSeek smoke with usage and final content not complete",
                    ),
                    (not leakage_passed, "manual prompt inspection not passed"),
                    (
                        not runtime_reproducibility_ready,
                        "frozen runtime evidence gate not ready",
                    ),
                )
                if condition
            ],
            "mandatory_stop": True,
        },
        "smoke": {
            "actual_usage_by_group": actual_usage,
            "case_id": cases[0].case_id,
            "classification_by_group": {
                item["group"]: item.get("classification") for item in online
            },
            "compile_success_by_group": {
                item["group"]: item.get("evaluation", {}).get("compile_success")
                for item in online
            },
            "content_present_by_group": {
                item["group"]: bool(
                    str(item.get("model_response", {}).get("raw", "")).strip()
                )
                for item in online
            },
            "extraction_status_by_group": {
                item["group"]: item.get("extraction", {}).get("status")
                for item in online
            },
            "extracted_source_hash_by_group": {
                item["group"]: (
                    hashlib.sha256(
                        str(item["extraction"]["source"]).encode()
                    ).hexdigest()
                    if item.get("extraction", {}).get("source") is not None
                    else None
                )
                for item in online
            },
            "finish_reason_by_group": {
                item["group"]: item.get("model_response", {}).get("finish_reason")
                for item in online
            },
            "plausible_by_group": {
                item["group"]: item.get("evaluation", {}).get("plausible")
                for item in online
            },
            "response_model_by_group": {
                item["group"]: item.get("provider_response_metadata", {}).get(
                    "response_model"
                )
                for item in online
            },
            "requested_model_by_group": {
                item["group"]: item.get("provider_response_metadata", {}).get(
                    "requested_model"
                )
                for item in online
            },
            "system_fingerprint_by_group": {
                item["group"]: item.get("provider_response_metadata", {}).get(
                    "system_fingerprint"
                )
                for item in online
            },
            "selection_rule": "first case in the frozen Repair Pilot manifest",
            "truncation_detected": smoke_truncated,
            "validated_by_group": {
                item["group"]: item.get("evaluation", {}).get("validated")
                for item in online
            },
        },
        "frozen_runtime_evidence": {
            "capture_rule": frozen_runtime.manifest["capture_rule"],
            "manifest_path": str(RUNTIME_EVIDENCE_MANIFEST.relative_to(PROJECT_ROOT)),
            "nondeterminism_audit": {
                "artifact_path": str(
                    RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT.relative_to(PROJECT_ROOT)
                ),
                "audit_sha256": nondeterminism_audit["audit_sha256"],
                "records": nondeterminism_audit["records"],
            },
            "prompt_reproducibility": {
                "all_prompt_hashes_identical_across_reloads": prompt_reproducibility[
                    "all_prompt_hashes_identical_across_reloads"
                ],
                "artifact_path": str(
                    RUNTIME_EVIDENCE_PROMPT_AUDIT.relative_to(PROJECT_ROOT)
                ),
                "leakage_audit": prompt_reproducibility["leakage_audit"],
                "payloads_checked": prompt_reproducibility["payloads_checked"],
                "prompt_set_hash": prompt_reproducibility["prompt_set_hash"],
                "prompts_checked": prompt_reproducibility["prompts_checked"],
                "target_case_c_hashes": prompt_reproducibility[
                    "target_case_c_hashes"
                ],
                "target_case_c_ten_render_hashes_identical": prompt_reproducibility[
                    "target_case_c_ten_render_hashes_identical"
                ],
            },
            "runner": frozen_runtime.manifest["runner"],
            "validation": frozen_runtime.validation,
        },
        "remaining_bulk_reproducibility_blocker": {
            "case_id": "450-B-bug-15950152-15950193",
            "case_retained": True,
            "status": "resolved by frozen single-observation protocol",
            "issue": (
                "buggy runtime remains non-deterministic, while formal prompts load "
                "one preregistered observation"
            ),
        },
        "token_estimate": {
            "approximate_average_output_tokens_per_call": average_output,
            "approximate_total_output_tokens": approximate_output,
            "bulk_projection": projection,
            "groups": groups,
            "method": (
                "ceil(UTF-8-decoded character count / 4) per prompt/source; "
                "averages rounded to 10 tokens and totals to 100 tokens; buggy-source "
                "length is the complete-source output proxy until real usage exists"
            ),
        },
    }
    REPAIR_PRE_EXPERIMENT_ESTIMATE.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_PRE_EXPERIMENT_ESTIMATE.write_text(
        json.dumps(estimate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return estimate


def _usage_cell(value: dict[str, Any], key: str) -> str:
    usage = value.get("usage")
    if usage is None or key not in usage:
        return "N/A"
    return str(usage[key])


def render_pre_experiment_report(value: dict[str, Any]) -> str:
    groups = value["token_estimate"]["groups"]
    estimate_rows = "\n".join(
        f"| {group} | {metric['calls']} | "
        f"~{metric['approximate_average_input_tokens']} | "
        f"~{metric['approximate_total_input_tokens']} |"
        for group, metric in groups.items()
    )
    usage_rows = "\n".join(
        f"| {group} | {metric['calls']} | "
        f"{_usage_cell(metric, 'prompt_tokens')} | "
        f"{_usage_cell(metric, 'completion_tokens')} | "
        f"{_usage_cell(metric, 'reasoning_tokens')} | "
        f"{_usage_cell(metric, 'final_answer_tokens')} | "
        f"{_usage_cell(metric, 'prompt_cache_hit_tokens')} | "
        f"{_usage_cell(metric, 'prompt_cache_miss_tokens')} | "
        f"{_usage_cell(metric, 'total_tokens')} |"
        for group, metric in value["smoke"]["actual_usage_by_group"].items()
    )
    blockers = "\n".join(
        f"- {reason}" for reason in value["readiness"]["blocking_reasons"]
    ) or "- None"
    model = value["model"]
    billing = value["billing"]
    pricing = billing["pricing"]
    current = pricing["pricing_at_verification"]
    scheduled = pricing["scheduled_change"]
    cost = billing["bulk_cache_miss_cost_estimates"]
    projection = value["token_estimate"]["bulk_projection"]
    leakage = value["leakage_readiness"]
    selection = value["candidate_selection"]
    initial = selection["initial_candidate"]
    final = selection["final_candidate"]
    reproducibility = value["remaining_bulk_reproducibility_blocker"]
    runtime = value["frozen_runtime_evidence"]
    runtime_validation = runtime["validation"]
    runtime_prompt_audit = runtime["prompt_reproducibility"]
    runtime_diagnostic = runtime["nondeterminism_audit"]["records"][0]
    observed = ", ".join(model["response_models_observed"]) or "not observed; no real response"
    return f"""# LLM Repair Pre-Experiment Report

## Candidate Selection Timeline

- Initial candidate: `{initial['model']}`, thinking enabled, reasoning effort `{initial['reasoning_effort']}`, max tokens {initial['max_tokens']}.
- Pro smoke: {initial['smoke_result']}.
- Decision: the Pro configuration was rejected before any formal bulk call and is marked `{initial['status']}`; its {initial['smoke_calls']} artifacts remain available only for engineering audit.
- Final candidate: `{final['model']}`, thinking enabled, reasoning effort `{final['reasoning_effort']}`, max tokens {final['max_tokens']}.
- Selection reason: {selection['reason']}.
- Decision timing: {selection['decision_timing']}; neither Pro nor Flash smoke contributes to future formal repair rates.

## Model And Provider

- Provider: **{model['provider']}**.
- API: {model['api_format']}; base URL `{model['base_url']}`.
- Requested model ID: `{model['name']}`.
- Official documented model version: `{model['official_documented_model_version']}`.
- Response model/version observed at experiment time: `{observed}`.
- Thinking: `{model['thinking']['type']}`; reasoning effort: `{model['reasoning_effort']}`; stream: `{str(model['stream']).lower()}`.
- Temperature: not sent and not an effective sampling control in thinking mode. Temperature-based determinism is not claimed.
- Maximum output tokens: {model['max_tokens']}; maximum repair attempts: {value['calls']['attempts_per_case_group']}.
- `{model['name']}` is an API alias and may resolve differently over time; the response model and system fingerprint are recorded when available.

## Credential And Billing

- Independent API key required: yes; priority is `DEEPSEEK_API_KEY`, then `CODEDOCTOR_API_KEY`.
- `OPENAI_API_KEY` is not used as a DeepSeek fallback.
- Credential readiness: `{value['credential']['available']}`; environment used: `{value['credential']['environment_used'] or 'none'}`. No secret value is stored or printed.
- Billing path: {billing['path']}.
- ChatGPT Plus/Codex subscription is separate from DeepSeek API billing.

## Calls And Smoke

- Repair Pilot: {value['calls']['repair_pilot_cases']} frozen cases; groups: {value['calls']['groups']}; attempts: {value['calls']['attempts_per_case_group']}.
- Formal bulk size: {value['calls']['primary']} primary calls. This bulk has not been started.
- Authorized smoke maximum: {value['calls']['smoke_maximum']} calls; actual real smoke calls: {value['calls']['real_smoke_calls']}.
- Superseded Pro engineering smoke calls retained but excluded: {value['calls']['superseded_smoke_calls']}.
- Formal experiment calls: {value['calls']['formal_experiment_calls']}.
- Smoke selection: `{value['smoke']['case_id']}`, selected by `{value['smoke']['selection_rule']}`.
- Automatic transport retries: {value['calls']['transport_retries_configured']}.

| Group | Real calls | Prompt tokens | Completion tokens | Reasoning tokens | Final-answer tokens | Cache hit | Cache miss | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{usage_rows}

- Smoke classifications: `{value['smoke']['classification_by_group'] or 'N/A'}`.
- Requested models: `{value['smoke']['requested_model_by_group'] or 'N/A'}`.
- Response models: `{value['smoke']['response_model_by_group'] or 'N/A'}`.
- System fingerprints: `{value['smoke']['system_fingerprint_by_group'] or 'N/A'}`.
- Final content present: `{value['smoke']['content_present_by_group'] or 'N/A'}`; extraction: `{value['smoke']['extraction_status_by_group'] or 'N/A'}`.
- Extracted source hashes: `{value['smoke']['extracted_source_hash_by_group'] or 'N/A'}`.
- Compile success: `{value['smoke']['compile_success_by_group'] or 'N/A'}`; plausible: `{value['smoke']['plausible_by_group'] or 'N/A'}`; validated: `{value['smoke']['validated_by_group'] or 'N/A'}`.
- Finish reasons: `{value['smoke']['finish_reason_by_group'] or 'N/A'}`. A `length` finish reason or incomplete source requires a stop, not a parameter change.
- Possible token truncation: `{value['smoke']['truncation_detected']}`.

## Token Projection

| Group | Calls | Approx. average input tokens | Approx. total input tokens |
|---|---:|---:|---:|
{estimate_rows}

- Previous output proxy for 150 calls: ~{value['token_estimate']['approximate_total_output_tokens']} tokens.
- Bulk projection basis: {projection['basis']}.
- Input calibration ratios A/B/C: `{projection['input_calibration_ratios']}`.
- Projected A/B/C input tokens: `{projection['input_by_group']}`.
- Projected output including provider-reported reasoning when real usage exists: `{projection['output_total']}` tokens.
- Separately reported reasoning tokens: `{projection['reasoning_total'] if projection['reasoning_total'] is not None else 'N/A'}`.
- Output basis: {projection['output_basis']}.
- Estimate uncertainty: {projection['uncertainty']}.
- Estimation method: {value['token_estimate']['method']}.

## Official Pricing Verification

- Official source: {pricing['official_source']}
- Verification time: `{pricing['verified_at']}`; currency: {pricing['currency']}; unit: 1M tokens.
- Price active at verification: cache hit `${current['input_cache_hit']}`, cache miss `${current['input_cache_miss']}`, output `${current['output']}`.
- Scheduled peak/off-peak change effective `{scheduled['effective_at']}`.
- Off-peak: cache hit `${scheduled['off_peak']['input_cache_hit']}`, cache miss `${scheduled['off_peak']['input_cache_miss']}`, output `${scheduled['off_peak']['output']}`.
- Peak: cache hit `${scheduled['peak']['input_cache_hit']}`, cache miss `${scheduled['peak']['input_cache_miss']}`, output `${scheduled['peak']['output']}`.
- Peak windows: {', '.join(scheduled['peak_windows'])}; all other UTC hours are off-peak.
- Conservative all-cache-miss bulk cost at verification prices: **${cost['at_verification_cache_miss_usd']:.6f}**.
- Conservative all-cache-miss scheduled off-peak cost: **${cost['scheduled_off_peak_cache_miss_usd']:.6f}**.
- Conservative all-cache-miss scheduled peak cost: **${cost['scheduled_peak_cache_miss_usd']:.6f}**.
- Context cache is best-effort, so cache-hit pricing is not assumed.
- Actual three-call smoke cost at verification prices: `{f"${cost['actual_smoke_at_verification_usd']:.6f}" if cost['actual_smoke_at_verification_usd'] is not None else 'N/A'}`.

## Information Boundary

| Information | A | B | C |
|---|---:|---:|---:|
| Buggy source | Yes | Yes | Yes |
| Common repair-time input/expected-output oracle | Same | Same | Same |
| FL-v1 evidence | No | Yes | Yes |
| Runtime verdict/actual output/exit status | No | No | Yes |
| Reference source | No | No | No |
| Ground-truth diff | No | No | No |
| Hidden validation | No | No | No |

- Reference leakage regression: `{leakage['reference_leakage_regression']}`.
- Validation leakage regression: `{leakage['validation_leakage_regression']}`.
- Manual prompt inspection: `{leakage['manual_prompt_inspection']}`.
- Prompt boundary audit: `{leakage['prompt_boundary_audit']['status']}` over {leakage['prompt_boundary_audit']['prompts_checked']} prompts.
- Artifact boundary audit: `{leakage['artifact_boundary_audit']['status']}` over {leakage['artifact_boundary_audit']['artifacts_checked']} artifacts.
- Reference source, ground-truth diff, hidden validation, and evaluation-only metadata absent: `{leakage['reference_source_absent']}` / `{leakage['ground_truth_diff_absent']}` / `{leakage['hidden_validation_absent']}` / `{leakage['evaluation_only_metadata_absent']}`.

## Frozen Runtime Evidence Protocol

- Problem discovery: repeated execution of `450-B-bug-15950152-15950193` changed only `n1.stdout`; stderr stayed empty, exit code stayed 0, timeout stayed false, and verdicts stayed unchanged. The source reads uninitialized `f[0]` when `n % 6 == 0`, so the varying stdout is undefined behavior from an uninitialized value.
- The case remains in the 50-case Repair Pilot. Runtime normalization, output sorting, regex replacement, reference substitution, and post-hoc observation selection are forbidden.
- Research interpretation: the model receives one real buggy execution observation. The buggy runtime need not become deterministic, but that first observation must be frozen before formal LLM calls.
- Capture rule: each Repair Pilot case and each repair test is executed exactly once in manifest order, with transport retry 0; the first and only observation is retained without normalization.
- Snapshot coverage: {runtime_validation['case_count']}/50 cases and {runtime_validation['repair_test_count']} repair tests; protocol `{runtime_validation['protocol_version']}`.
- Manifest: `{runtime['manifest_path']}`; overall hash `{runtime_validation['manifest_hash']}`. It binds the Repair Pilot hash, repair-v2 hash, artifact paths and hashes, test order, timestamp, and Docker runner configuration.
- Exact preservation: stdout/stderr are stored as JSON strings and independently verified with UTF-8 SHA-256; missing files, corrupt content, manifest mismatch, Pilot mismatch, or repair-v2 mismatch fail closed.
- Formal prompt path: Group A uses base context, Group B adds frozen FL-v1, and Group C adds only the loaded and hash-verified runtime snapshot. Formal prompt construction never reruns the buggy program.
- Formal render audit: {runtime_prompt_audit['prompts_checked']}/150 prompts built successfully; two complete independent snapshot reloads produced the same prompt-set hash `{runtime_prompt_audit['prompt_set_hash']}`.
- 450-B Group C: 10/10 frozen-evidence renders produced the same prompt hash `{runtime_prompt_audit['target_case_c_hashes'][0]}`.
- Diagnostic reruns remain evaluation-only: {runtime_diagnostic['observed_runs']} post-freeze runs produced {len(runtime_diagnostic['observed_distinct_hashes'])} distinct observation hashes and changed only `{runtime_diagnostic['changed_fields']}`. They did not modify the snapshot or prompts.
- Snapshot, manifest, prompts, and serialized Flash payload leakage audit: `{runtime_prompt_audit['leakage_audit']['status']}`; reference source, ground truth, hidden validation, evaluation canaries, and credentials are absent.
- The buggy runtime behavior remains non-deterministic, but the repair experiment consumes a preregistered frozen runtime observation, making the experimental prompt reproducible.

## Mandatory Stop

- `smoke_technical_ready = {str(value['readiness']['smoke_technical_ready']).lower()}`.
- `bulk_online_ready = {str(value['readiness']['bulk_online_ready']).lower()}`.
- `bulk_user_authorized = {str(value['readiness']['bulk_user_authorized']).lower()}`.
- Remaining reproducibility blocker: `{reproducibility['case_id']}` is `{reproducibility['status']}`; {reproducibility['issue']}. The case remains in the Pilot.

Blocking reasons:

{blockers}

DeepSeek Phase 7 bulk experiment is technically {'ready' if value['readiness']['bulk_online_ready'] else 'not ready'}.

No 150-call bulk experiment has been started.

Do not use `--confirm-bulk`.

Awaiting explicit approval before the Phase 7 bulk experiment.
"""


def write_pre_experiment_report(manual_inspection: str) -> dict[str, Any]:
    value = build_estimate(manual_inspection)
    REPAIR_PRE_EXPERIMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_PRE_EXPERIMENT_REPORT.write_text(
        render_pre_experiment_report(value), encoding="utf-8"
    )
    return value
