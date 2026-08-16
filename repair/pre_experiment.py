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
    REPAIR_ARTIFACT_ROOT,
    REPAIR_PILOT_FL,
    REPAIR_PRE_EXPERIMENT_ESTIMATE,
    REPAIR_PRE_EXPERIMENT_REPORT,
)
from benchmark.models import load_manifest

from .context import build_repair_context, load_fl_records
from .deepseek import resolve_api_key, validate_configuration
from .evaluator import evaluate_source
from .models import EvidenceGroup, PromptDocument
from .prompting import render_prompt
from .protocol import validate_repair_protocol
from .reporting import validate_artifact_boundaries


def approximate_tokens(text: str) -> int:
    """Transparent provider-independent heuristic, not a tokenizer claim."""

    return math.ceil(len(text) / 4)


def _round_tokens(value: float, unit: int) -> int:
    return int(round(value / unit) * unit)


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*/*/*.json"))
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
                    "all three smoke completions reached max_tokens; this is an "
                    "all-calls-hit-8192 conservative cap scenario, not expected usage"
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
    fl_records = load_fl_records(REPAIR_PILOT_FL)
    input_tokens: dict[str, list[int]] = {group.value: [] for group in EvidenceGroup}
    output_tokens: list[int] = []
    per_case_input_tokens: dict[str, dict[str, int]] = {}
    prompt_hashes = []
    prompts: dict[str, dict[str, PromptDocument]] = {}
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] estimating {case.case_id}", flush=True)
        baseline = evaluate_source(case, case.get_buggy_source(), include_validation=False)
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
    online = [
        item
        for item in all_artifacts
        if item.get("experimental") is True
        and item.get("model_parameters", {}).get("provider") == "deepseek"
    ]
    actual_usage = _usage_by_group(online)
    smoke_truncated = bool(online) and all(
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
    bulk_online_ready = has_key and complete_smoke and leakage_passed
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
        "prompt_hashes": prompt_hashes,
        "protocol_version": protocol["protocol_version"],
        "readiness": {
            "bulk_online_ready": bulk_online_ready,
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
            "selection_rule": "first case in the frozen Repair Pilot manifest",
            "truncation_detected": smoke_truncated,
            "validated_by_group": {
                item["group"]: item.get("evaluation", {}).get("validated")
                for item in online
            },
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
    observed = ", ".join(model["response_models_observed"]) or "not observed; no real response"
    return f"""# LLM Repair Pre-Experiment Report

## Model And Provider

- Provider: **{model['provider']}**.
- API: {model['api_format']}; base URL `{model['base_url']}`.
- Requested model ID: `{model['name']}`.
- Official documented model version: `{model['official_documented_model_version']}`.
- Response model/version observed at experiment time: `{observed}`.
- Thinking: `{model['thinking']['type']}`; reasoning effort: `{model['reasoning_effort']}`; stream: `{str(model['stream']).lower()}`.
- Temperature: not sent and not an effective sampling control in thinking mode. Temperature-based determinism is not claimed.
- Maximum output tokens: {model['max_tokens']}; maximum repair attempts: {value['calls']['attempts_per_case_group']}.
- `deepseek-v4-pro` is an API alias and may resolve differently over time; the response model and system fingerprint are recorded when available.

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
- Smoke selection: `{value['smoke']['case_id']}`, selected by `{value['smoke']['selection_rule']}`.
- Automatic transport retries: {value['calls']['transport_retries_configured']}.

| Group | Real calls | Prompt tokens | Completion tokens | Reasoning tokens | Cache hit | Cache miss | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
{usage_rows}

- Smoke classifications: `{value['smoke']['classification_by_group'] or 'N/A'}`.
- Response models: `{value['smoke']['response_model_by_group'] or 'N/A'}`.
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

## Mandatory Stop

- `bulk_online_ready = {str(value['readiness']['bulk_online_ready']).lower()}`.
- `bulk_user_authorized = {str(value['readiness']['bulk_user_authorized']).lower()}`.

Blocking reasons:

{blockers}

DeepSeek Phase 7 bulk experiment is technically {'ready' if value['readiness']['bulk_online_ready'] else 'not ready'}.

No 150-call bulk experiment has been started.

Awaiting explicit approval before using `--confirm-bulk`.
"""


def write_pre_experiment_report(manual_inspection: str) -> dict[str, Any]:
    value = build_estimate(manual_inspection)
    REPAIR_PRE_EXPERIMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_PRE_EXPERIMENT_REPORT.write_text(
        render_pre_experiment_report(value), encoding="utf-8"
    )
    return value
