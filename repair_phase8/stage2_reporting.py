"""Offline validation and paired analysis for the Phase 8 Stage 2 artifacts."""

import hashlib
import json
import math
import re
from collections import Counter
from itertools import product
from pathlib import Path
from typing import Any, Sequence

from benchmark.config import (
    DEEPSEEK_FORMAL_PRICING_SNAPSHOT,
    PHASE8_ARTIFACT_ROOT,
    PHASE8_RANDOM_SEED,
)
from benchmark.models import BenchmarkCase

from .partition import canonical_hash, second_round_order


CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")
CREDENTIAL_PATTERN = re.compile(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}")
FEEDBACK_HEADING = "## Failed repair-time execution feedback"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nearest_rank(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * probability) - 1]


def paired_statistics(outcomes: Sequence[tuple[bool, bool]]) -> dict[str, Any]:
    if not outcomes:
        raise ValueError("paired analysis requires at least one case")
    both_success = sum(retry and feedback for retry, feedback in outcomes)
    retry_fail_feedback_success = sum(
        not retry and feedback for retry, feedback in outcomes
    )
    retry_success_feedback_fail = sum(
        retry and not feedback for retry, feedback in outcomes
    )
    both_fail = len(outcomes) - (
        both_success + retry_fail_feedback_success + retry_success_feedback_fail
    )
    differences = [int(feedback) - int(retry) for retry, feedback in outcomes]
    if len(differences) > 8:
        raise ValueError("exact bootstrap enumeration is bounded to eight pairs")
    bootstrap = [
        sum(sample) / len(differences)
        for sample in product(differences, repeat=len(differences))
    ]
    discordant = retry_fail_feedback_success + retry_success_feedback_fail
    smaller = min(retry_fail_feedback_success, retry_success_feedback_fail)
    if discordant == 0:
        mcnemar_p = 1.0
    else:
        tail = sum(math.comb(discordant, index) for index in range(smaller + 1))
        mcnemar_p = min(1.0, 2 * tail / (2**discordant))
    return {
        "bootstrap_95_ci": {
            "lower": _nearest_rank(bootstrap, 0.025),
            "method": "exact enumeration of empirical paired bootstrap resamples",
            "resamples": len(bootstrap),
            "upper": _nearest_rank(bootstrap, 0.975),
        },
        "both_fail": both_fail,
        "both_success": both_success,
        "feedback_minus_retry": sum(differences) / len(differences),
        "feedback_validated": sum(feedback for _, feedback in outcomes),
        "gross_feedback_rescue_rate_among_retry_failures": (
            retry_fail_feedback_success
            / (retry_fail_feedback_success + both_fail)
            if retry_fail_feedback_success + both_fail
            else None
        ),
        "mcnemar_exact": {
            "discordant_pairs": discordant,
            "p_value_two_sided": mcnemar_p,
        },
        "pair_count": len(outcomes),
        "retry_fail_feedback_success": retry_fail_feedback_success,
        "retry_success_feedback_fail": retry_success_feedback_fail,
        "retry_validated": sum(retry for retry, _ in outcomes),
    }


def _usage(record: dict[str, Any]) -> dict[str, int | str]:
    value = record.get("provider_response_metadata", {}).get("usage", {})
    result: dict[str, int | str] = {}
    for key in (
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "completion_tokens",
        "total_tokens",
        "final_answer_tokens",
    ):
        item = value.get(key)
        result[key] = item if isinstance(item, int) else "N/A"
    reasoning = value.get("completion_tokens_details", {}).get("reasoning_tokens")
    result["reasoning_tokens"] = reasoning if isinstance(reasoning, int) else "N/A"
    return result


def _sum_usage(entries: Sequence[dict[str, Any]]) -> dict[str, int | str]:
    keys = entries[0]["usage"]
    result: dict[str, int | str] = {}
    for key in keys:
        values = [entry["usage"][key] for entry in entries]
        result[key] = sum(values) if all(isinstance(item, int) for item in values) else "N/A"
    return result


def _cost(usage: dict[str, int | str], pricing: dict[str, Any]) -> float | str:
    keys = ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "completion_tokens")
    if not all(isinstance(usage[key], int) for key in keys):
        return "N/A"
    rates = pricing["prices"]
    return round(
        (
            usage["prompt_cache_hit_tokens"] * rates["input_cache_hit"]
            + usage["prompt_cache_miss_tokens"] * rates["input_cache_miss"]
            + usage["completion_tokens"] * rates["output"]
        )
        / pricing["price_unit_tokens"],
        8,
    )


def build_stage2_result_manifest(
    cases: Sequence[BenchmarkCase],
    stage1: dict[str, Any],
    cohort: dict[str, Any],
    prompt_audit: dict[str, Any],
) -> dict[str, Any]:
    by_case = {case.case_id: case for case in cases}
    expected_prompts = {
        (item["case_id"], item["arm"]): item
        for item in prompt_audit["prompt_records"]
    }
    entries = []
    prompt_users: dict[str, dict[str, str]] = {}
    leakage_violations = []
    for cohort_entry in cohort["entries"]:
        case_id = cohort_entry["case_id"]
        case = by_case[case_id]
        order = second_round_order(case_id, PHASE8_RANDOM_SEED)
        prompt_users[case_id] = {}
        for order_index, arm in enumerate(order):
            paths = list((PHASE8_ARTIFACT_ROOT / arm / case_id).glob("*.json"))
            if len(paths) != 1:
                raise ValueError(f"expected one {arm} artifact for {case_id}")
            path = paths[0]
            text = path.read_text(encoding="utf-8", errors="replace")
            record = json.loads(text)
            prompt = record.get("prompt", {})
            if (
                record.get("completed") is not True
                or record.get("case_id") != case_id
                or record.get("arm") != arm
                or record.get("attempt") != 2
                or record.get("first_patch_hash") != cohort_entry["first_patch_hash"]
                or record.get("initial_prompt_hash")
                != cohort_entry["initial_prompt_hash"]
                or prompt.get("hash") != expected_prompts[(case_id, arm)]["prompt_hash"]
                or record.get("model_parameters", {}).get("provider") != "deepseek"
            ):
                raise ValueError(f"frozen Stage 2 binding mismatch for {case_id}/{arm}")
            prompt_text = str(prompt.get("system", "")) + "\n" + str(
                prompt.get("user", "")
            )
            prompt_users[case_id][arm] = str(prompt.get("user", ""))
            if any(canary in prompt_text for canary in CANARIES):
                leakage_violations.append(f"{case_id}/{arm}: evaluation canary")
            if CREDENTIAL_PATTERN.search(prompt_text) or CREDENTIAL_PATTERN.search(text):
                leakage_violations.append(f"{case_id}/{arm}: credential-like value")
            reference = case.get_reference_source(evaluation_only=True)
            if reference and reference in prompt_text:
                leakage_violations.append(f"{case_id}/{arm}: reference source")
            if any(
                test_id in prompt_text
                for test_id in case.metadata["phase8"]["hidden_test_ids"]
            ):
                leakage_violations.append(f"{case_id}/{arm}: hidden validation id")
            reasoning = record.get("provider_response_metadata", {}).get(
                "reasoning_content"
            )
            if isinstance(reasoning, str):
                leakage_violations.append(f"{case_id}/{arm}: raw reasoning")
            has_feedback = FEEDBACK_HEADING in prompt_text
            if has_feedback != (arm == "feedback"):
                raise ValueError(f"R/F feedback boundary mismatch for {case_id}/{arm}")
            evaluation = record.get("evaluation") or {}
            response = record.get("model_response") or {}
            metadata = record.get("provider_response_metadata") or {}
            entries.append(
                {
                    "arm": arm,
                    "arm_attempt": 1,
                    "artifact_bytes": path.stat().st_size,
                    "artifact_sha256": _sha256_file(path),
                    "case_id": case_id,
                    "classification": record.get("classification"),
                    "finish_reason": response.get("finish_reason", "N/A"),
                    "first_patch_hash": record.get("first_patch_hash"),
                    "hidden_validation_passed": evaluation.get("validated", False),
                    "order_index": order_index,
                    "prompt_hash": prompt.get("hash"),
                    "provider_received": bool(record.get("model_response")),
                    "repair_round": 2,
                    "repair_time_success": record.get("repair_time_results", {}).get(
                        "success", False
                    ),
                    "response_hash": response.get("response_hash"),
                    "response_model": metadata.get("response_model", "N/A"),
                    "system_fingerprint": metadata.get("system_fingerprint", "N/A"),
                    "usage": _usage(record),
                    "validated": evaluation.get("validated", False),
                }
            )
        retry_user = prompt_users[case_id]["retry_control"]
        feedback_user = prompt_users[case_id]["feedback"]
        if not feedback_user.startswith(retry_user):
            raise ValueError(f"F does not preserve the exact R prefix for {case_id}")
    if leakage_violations:
        raise ValueError(f"Stage 2 leakage detected: {leakage_violations}")

    by_pair = {
        case_id: {
            entry["arm"]: entry
            for entry in entries
            if entry["case_id"] == case_id
        }
        for case_id in (item["case_id"] for item in cohort["entries"])
    }
    outcomes = [
        (
            by_pair[case_id]["retry_control"]["validated"],
            by_pair[case_id]["feedback"]["validated"],
        )
        for case_id in by_pair
    ]
    paired = paired_statistics(outcomes)
    pricing = json.loads(
        DEEPSEEK_FORMAL_PRICING_SNAPSHOT.read_text(encoding="utf-8")
    )
    retry_entries = [item for item in entries if item["arm"] == "retry_control"]
    feedback_entries = [item for item in entries if item["arm"] == "feedback"]
    usage_retry = _sum_usage(retry_entries)
    usage_feedback = _sum_usage(feedback_entries)
    usage_total = _sum_usage(entries)
    initial_validated = 85
    result: dict[str, Any] = {
        "artifact_set_hash": canonical_hash(entries),
        "calls": {
            "attempted": len(entries),
            "provider_failures": sum(
                item["classification"] == "provider_failure" for item in entries
            ),
            "received": sum(item["provider_received"] for item in entries),
        },
        "cohort_manifest_hash": cohort["overall_manifest_hash"],
        "end_to_end": {
            "S0_initial_only": {"rate": initial_validated / 100, "validated": initial_validated},
            "SF_initial_plus_feedback": {
                "rate": (initial_validated + paired["feedback_validated"]) / 100,
                "validated": initial_validated + paired["feedback_validated"],
            },
            "SR_initial_plus_retry": {
                "rate": (initial_validated + paired["retry_validated"]) / 100,
                "validated": initial_validated + paired["retry_validated"],
            },
            "denominator": 100,
        },
        "entries": entries,
        "failure_modes": {
            "feedback": dict(
                sorted(Counter(item["classification"] for item in feedback_entries).items())
            ),
            "retry_control": dict(
                sorted(Counter(item["classification"] for item in retry_entries).items())
            ),
        },
        "leakage_audit": {
            "credential_absent": "passed",
            "evaluation_canaries_absent": "passed",
            "f_only_bounded_execution_feedback": "passed",
            "hidden_validation_absent": "passed",
            "raw_reasoning_absent": "passed",
            "reference_source_absent": "passed",
            "status": "passed",
        },
        "paired": paired,
        "pricing": pricing,
        "prompt_audit_hash": prompt_audit["overall_manifest_hash"],
        "protocol_version": "phase8-stage2-result-manifest-v1",
        "stage1_manifest_hash": stage1["overall_manifest_hash"],
        "usage_and_cost": {
            "feedback": {"cost_usd": _cost(usage_feedback, pricing), "tokens": usage_feedback},
            "retry_control": {"cost_usd": _cost(usage_retry, pricing), "tokens": usage_retry},
            "total": {"cost_usd": _cost(usage_total, pricing), "tokens": usage_total},
        },
    }
    result["overall_manifest_hash"] = canonical_hash(result)
    return result


def render_final_report(value: dict[str, Any]) -> str:
    paired = value["paired"]
    end = value["end_to_end"]
    total = value["usage_and_cost"]["total"]
    rows = []
    for case_id in dict.fromkeys(item["case_id"] for item in value["entries"]):
        arms = {
            item["arm"]: item for item in value["entries"] if item["case_id"] == case_id
        }
        rows.append(
            f"| {case_id} | {arms['retry_control']['classification']} | "
            f"{arms['feedback']['classification']} | "
            f"{str(arms['retry_control']['validated']).lower()} | "
            f"{str(arms['feedback']['validated']).lower()} |"
        )
    ci = paired["bootstrap_95_ci"]
    return f"""# Phase 8 Controlled Execution Feedback Formal Experiment

## Research Question

For the same failed Stage 1 patch, does one retry with bounded execution feedback validate more often than the same retry opportunity without feedback?

## Frozen Cohort And Stage 1 Baseline

Stage 1 validated 85/100 patches. The frozen eligible cohort contains `M=6` repair-time failures. Each case used the same frozen first patch in R and F. R contains no first-patch execution feedback; F adds only Runtime Evidence Renderer v2 bounded repair-time failure evidence.

Stage 2 attempted/received/provider-failed calls: `{value['calls']['attempted']} / {value['calls']['received']} / {value['calls']['provider_failures']}`. Each arm made one request with zero transport retries; the artifact field `repair_round=2` denotes the second repair round, while `arm_attempt=1` denotes one request per arm.

## Paired Results

| Outcome | Cases |
| --- | ---: |
| Both validated | {paired['both_success']} |
| R failed, F validated | {paired['retry_fail_feedback_success']} |
| R validated, F failed | {paired['retry_success_feedback_fail']} |
| Both failed | {paired['both_fail']} |

- R validated: `{paired['retry_validated']}/6`.
- F validated: `{paired['feedback_validated']}/6`.
- F-R validated difference: `{paired['feedback_minus_retry']:.6f}` ({paired['feedback_minus_retry'] * 100:.1f} percentage points).
- Gross F rescue among R failures: `{paired['gross_feedback_rescue_rate_among_retry_failures']:.6f}`.
- Paired bootstrap 95% CI for F-R: `[{ci['lower']:.6f}, {ci['upper']:.6f}]`, using {ci['method']} ({ci['resamples']} resamples).
- Exact two-sided McNemar: `p={paired['mcnemar_exact']['p_value_two_sided']:.6f}` with {paired['mcnemar_exact']['discordant_pairs']} discordant pairs.

These are paired case-level observations. With `M=6`, the interval is wide and the study has little power for statistical generalization.

## Case Outcomes

| Case | R classification | F classification | R validated | F validated |
| --- | --- | --- | ---: | ---: |
{chr(10).join(rows)}

## End-To-End Validated Rates

- S0, Initial only: `{end['S0_initial_only']['validated']}/100 = {end['S0_initial_only']['rate']:.1%}`.
- SR, Initial + retry without feedback: `{end['SR_initial_plus_retry']['validated']}/100 = {end['SR_initial_plus_retry']['rate']:.1%}`.
- SF, Initial + feedback retry: `{end['SF_initial_plus_feedback']['validated']}/100 = {end['SF_initial_plus_feedback']['rate']:.1%}`.

## Failure Analysis

- R classifications: `{json.dumps(value['failure_modes']['retry_control'], sort_keys=True)}`.
- F classifications: `{json.dumps(value['failure_modes']['feedback'], sort_keys=True)}`.
- One R repair-time failure was rescued by F. One R validated patch became a length-truncated invalid F output. One case in each arm passed repair-time tests but failed Hidden Validation.

## Token Usage And Cost

- Total prompt/cache-hit/cache-miss tokens: `{total['tokens']['prompt_tokens']} / {total['tokens']['prompt_cache_hit_tokens']} / {total['tokens']['prompt_cache_miss_tokens']}`.
- Total reasoning/final-answer/completion/total tokens: `{total['tokens']['reasoning_tokens']} / {total['tokens']['final_answer_tokens']} / {total['tokens']['completion_tokens']} / {total['tokens']['total_tokens']}`.
- Usage-based Stage 2 cost estimate: `${total['cost_usd']:.8f}`.
- R tokens/cost: `{json.dumps(value['usage_and_cost']['retry_control'], sort_keys=True)}`.
- F tokens/cost: `{json.dumps(value['usage_and_cost']['feedback'], sort_keys=True)}`.
- R/F details and provider metadata are retained in the hashed result manifest. Raw Stage 2 artifacts remain local and are excluded from Git because they are large reproducible records.

## Integrity And Limitations

- Stage 2 artifact-set hash: `{value['artifact_set_hash']}`.
- Stage 2 result manifest hash: `{value['overall_manifest_hash']}`.
- Leakage audit: `{value['leakage_audit']['status']}`.
- `Validated Patch != Formally Correct Patch`: validation is limited to the registered Base, Feedback, and Hidden tests.
- `M=6` limits statistical generalization. Neither a large percentage nor a p-value would justify population-level claims here.

## Conclusion

In this frozen six-case cohort, execution feedback did not improve the aggregate validated count over retry alone: both validated 4/6, with one F rescue and one opposite-direction loss. The result is paired case-level evidence of heterogeneous effects, not evidence of a general advantage or disadvantage.
"""
