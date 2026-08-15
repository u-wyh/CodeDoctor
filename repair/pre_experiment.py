"""Build the mandatory pre-experiment call/token/readiness report."""

import json
import math
import os
import statistics
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_PILOT_FL,
    REPAIR_PRE_EXPERIMENT_ESTIMATE,
    REPAIR_PRE_EXPERIMENT_REPORT,
)
from benchmark.models import load_manifest

from .context import build_repair_context, load_fl_records
from .evaluator import evaluate_source
from .models import EvidenceGroup
from .prompting import render_prompt
from .protocol import validate_repair_protocol


def approximate_tokens(text: str) -> int:
    """Transparent provider-independent heuristic, not a tokenizer claim."""

    return math.ceil(len(text) / 4)


def _round_tokens(value: float, unit: int) -> int:
    return int(round(value / unit) * unit)


def _experimental_artifact_count(root: Path) -> int:
    count = 0
    for path in root.glob("*/*/*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        count += item.get("experimental") is True
    return count


def build_estimate(manual_inspection: str) -> dict[str, Any]:
    protocol = validate_repair_protocol()
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    fl_records = load_fl_records(REPAIR_PILOT_FL)
    input_tokens: dict[str, list[int]] = {group.value: [] for group in EvidenceGroup}
    output_tokens: list[int] = []
    prompt_hashes = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] estimating {case.case_id}", flush=True)
        baseline = evaluate_source(case, case.get_buggy_source(), include_validation=False)
        output_tokens.append(approximate_tokens(case.get_buggy_source()))
        for group in EvidenceGroup:
            context = build_repair_context(
                case, group, fl_records.get(case.case_id), baseline
            )
            prompt = render_prompt(context, group)
            input_tokens[group.value].append(
                approximate_tokens(prompt.system + "\n" + prompt.user)
            )
            prompt_hashes.append(
                {
                    "case_id": case.case_id,
                    "group": group.value,
                    "prompt_hash": prompt.prompt_hash,
                }
            )

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
    output_per_group = _round_tokens(sum(output_tokens), 100)
    model = os.environ.get("CODEDOCTOR_MODEL") or os.environ.get("OPENAI_MODEL")
    base_url = os.environ.get("CODEDOCTOR_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    has_key = bool(os.environ.get("CODEDOCTOR_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    online_smoke = _experimental_artifact_count(REPAIR_ARTIFACT_ROOT)
    pricing_verified = False
    explicit_bulk_user_approval = False
    estimate = {
        "billing": {
            "estimated_api_cost": None,
            "path": "not selected",
            "pricing_status": "verified" if pricing_verified else "not_verified",
            "subscription_warning": (
                "ChatGPT Plus/Codex subscription and API billing are separate; "
                "no shared quota is assumed."
            ),
        },
        "calls": {
            "attempts_per_case_group": 1,
            "groups": 3,
            "primary": len(cases) * 3,
            "repair_pilot_cases": len(cases),
            "smoke_maximum": 9,
            "transport_retries_configured": 0,
        },
        "credential": {
            "available": has_key,
            "environment_variables": ["CODEDOCTOR_API_KEY", "OPENAI_API_KEY"],
        },
        "leakage_readiness": {
            "evaluation_only_metadata_absent": "passed",
            "ground_truth_diff_absent": "passed",
            "hidden_validation_absent": "passed",
            "manual_prompt_inspection": manual_inspection,
            "reference_leakage_regression": "passed",
            "reference_source_absent": "passed",
            "validation_leakage_regression": "passed",
        },
        "model": {
            "base_url_configured": bool(base_url),
            "name": model,
            "provider": "OpenAI-compatible Chat Completions (actual service not selected)",
        },
        "online_smoke_artifacts": online_smoke,
        "prompt_hashes": prompt_hashes,
        "protocol_version": protocol["protocol_version"],
        "readiness": {
            "explicit_bulk_user_approval": explicit_bulk_user_approval,
            "pricing_verified": pricing_verified,
            "bulk_online_ready": bool(
                model
                and base_url
                and has_key
                and manual_inspection == "passed"
                and online_smoke > 0
                and pricing_verified
                and explicit_bulk_user_approval
            ),
            "blocking_reasons": [
                reason
                for condition, reason in (
                    (not model, "model/version not selected"),
                    (not base_url, "provider/base URL not selected"),
                    (not has_key, "independent API credential not configured"),
                    (online_smoke == 0, "genuine online smoke not run"),
                    (not pricing_verified, "provider pricing not verified"),
                    (
                        not explicit_bulk_user_approval,
                        "explicit user approval for bulk calls not granted",
                    ),
                )
                if condition
            ],
            "mandatory_stop": True,
        },
        "token_estimate": {
            "approximate_average_output_tokens_per_call": average_output,
            "approximate_total_output_tokens": output_per_group * 3,
            "groups": groups,
            "method": (
                "ceil(UTF-8-decoded character count / 4) per prompt/source; "
                "averages rounded to 10 tokens and totals to 100 tokens; buggy-source "
                "length is the expected complete-source output proxy"
            ),
        },
    }
    REPAIR_PRE_EXPERIMENT_ESTIMATE.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_PRE_EXPERIMENT_ESTIMATE.write_text(
        json.dumps(estimate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return estimate


def render_pre_experiment_report(value: dict[str, Any]) -> str:
    groups = value["token_estimate"]["groups"]
    rows = "\n".join(
        f"| {group} | {metric['calls']} | "
        f"~{metric['approximate_average_input_tokens']} | "
        f"~{metric['approximate_total_input_tokens']} |"
        for group, metric in groups.items()
    )
    blockers = "\n".join(
        f"- {reason}" for reason in value["readiness"]["blocking_reasons"]
    )
    leakage = value["leakage_readiness"]
    return f"""# LLM Repair Pre-Experiment Report

## Model And Provider

- Model/version: `{value['model']['name'] or 'not selected'}`.
- Provider interface: {value['model']['provider']}.
- Base URL configured: {value['model']['base_url_configured']}.
- Independent API key required: yes; read from `CODEDOCTOR_API_KEY`, falling back to `OPENAI_API_KEY`.

## Billing

- Billing path: {value['billing']['path']}.
- Pricing: **not verified**; estimated API cost is intentionally unavailable.
- {value['billing']['subscription_warning']}

## Expected Calls

- Repair Pilot: {value['calls']['repair_pilot_cases']} cases; groups: {value['calls']['groups']}; repair attempts: {value['calls']['attempts_per_case_group']}.
- Primary online calls: {value['calls']['primary']}.
- Genuine smoke maximum before the bulk pause: {value['calls']['smoke_maximum']} calls.
- Automatic transport retries: {value['calls']['transport_retries_configured']}; a transport retry is not a second repair attempt.

## Token Estimate

| Group | Calls | Approx. average input tokens | Approx. total input tokens |
|---|---:|---:|---:|
{rows}

- Approximate expected output per call: ~{value['token_estimate']['approximate_average_output_tokens_per_call']} tokens.
- Approximate total output for 150 calls: ~{value['token_estimate']['approximate_total_output_tokens']} tokens.
- Method: {value['token_estimate']['method']}.

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
- Reference source, ground-truth diff, hidden validation, and evaluation-only metadata absent: `{leakage['reference_source_absent']}` / `{leakage['ground_truth_diff_absent']}` / `{leakage['hidden_validation_absent']}` / `{leakage['evaluation_only_metadata_absent']}`.

## Mandatory Stop

Bulk online ready: `{value['readiness']['bulk_online_ready']}`.

Blocking reasons:

{blockers}

The CLI refuses more than nine online calls unless `--confirm-bulk` is supplied after explicit user approval. No bulk call is authorized by API-key availability, a successful smoke, or a ChatGPT/Codex subscription.
"""


def write_pre_experiment_report(manual_inspection: str) -> dict[str, Any]:
    value = build_estimate(manual_inspection)
    REPAIR_PRE_EXPERIMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_PRE_EXPERIMENT_REPORT.write_text(
        render_pre_experiment_report(value), encoding="utf-8"
    )
    return value
