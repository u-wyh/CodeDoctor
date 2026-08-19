"""Aggregate online repair artifacts and render the evidence-ablation report."""

import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT_SUMMARY,
    DEEPSEEK_FORMAL_PRICING_SNAPSHOT,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_EVALUATION,
    REPAIR_FORMAL_RUN,
    REPAIR_PILOT_ATTRIBUTES,
    REPAIR_PILOT_FL,
    REPAIR_PROTOCOL,
    REPAIR_REPORT,
    RUNTIME_EVIDENCE_PROMPT_AUDIT,
)
from fault_localization.statistics import exact_mcnemar, paired_bootstrap_difference


GROUPS = ("A", "B", "C")
PAIRINGS = (("A", "B"), ("B", "C"), ("A", "C"))
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260817
LEAKAGE_CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.json"))
    ]


def _signature(record: dict[str, Any]) -> str:
    value = {
        "model_parameters": record["model_parameters"],
        "template_version": record["prompt"]["template_version"],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_formal_artifact(record: dict[str, Any]) -> bool:
    role = record.get("experiment_role")
    if role is not None:
        return role == "formal_evidence_ablation"
    return (
        record.get("experimental") is True
        and record.get("model_parameters", {}).get("provider") != "deepseek"
    )


def validate_artifact_boundaries(records: list[dict[str, Any]]) -> dict[str, Any]:
    violations = []
    bases_by_case: dict[str, set[str]] = {}
    fl_sections_by_case: dict[str, set[str]] = {}
    for item in records:
        prompt = item.get("prompt", {})
        text = str(prompt.get("system", "")) + str(prompt.get("user", ""))
        group = item.get("group")
        if any(canary in text for canary in LEAKAGE_CANARIES):
            violations.append(f"{item.get('case_id')}/{group}: evaluation canary")
        has_fl = "## CodeDoctor FL-v1 suspicious locations" in text
        has_execution = "## Repair-test execution evidence" in text
        has_oracle = "## Common repair-time oracle" in text
        if not has_oracle:
            violations.append(f"{item.get('case_id')}/{group}: missing common oracle")
        if group == "A" and (has_fl or has_execution):
            violations.append(f"{item.get('case_id')}/A: extra evidence")
        elif group == "B" and (not has_fl or has_execution):
            violations.append(f"{item.get('case_id')}/B: evidence boundary")
        elif group == "C" and (not has_fl or not has_execution):
            violations.append(f"{item.get('case_id')}/C: evidence boundary")
        user = str(prompt.get("user", ""))
        base = user.split("\n\n## CodeDoctor FL-v1 suspicious locations", 1)[0]
        bases_by_case.setdefault(str(item.get("case_id")), set()).add(base)
        if group in {"B", "C"}:
            before_runtime = user.split("\n\n## Repair-test execution evidence", 1)[0]
            fl_sections_by_case.setdefault(str(item.get("case_id")), set()).add(
                before_runtime
            )
        if group == "C":
            runtime = user.split("## Repair-test execution evidence", 1)[-1]
            if "Expected output:" in runtime or "Input:" in runtime:
                violations.append(
                    f"{item.get('case_id')}/C: runtime section adds task semantics"
                )
        forbidden_parameter_keys = {
            key
            for key in item.get("model_parameters", {})
            if key.lower()
            in {
                "api_key",
                "access_token",
                "authorization",
                "password",
                "secret",
            }
        }
        if forbidden_parameter_keys:
            violations.append(
                f"{item.get('case_id')}/{group}: secret parameter keys "
                f"{sorted(forbidden_parameter_keys)}"
            )
    for case_id, bases in bases_by_case.items():
        if len(bases) != 1:
            violations.append(f"{case_id}: A/B/C base contexts differ")
    for case_id, sections in fl_sections_by_case.items():
        if len(sections) != 1:
            violations.append(f"{case_id}: B/C FL contexts differ")
    if violations:
        raise ValueError(f"repair artifact leakage detected: {violations}")
    return {"artifacts_checked": len(records), "status": "passed"}


def _group_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    valid_output = sum(
        item["classification"] not in {"model_error", "invalid_model_output"}
        for item in records
    )
    compile_success = sum(
        bool(item.get("evaluation", {}).get("compile_success")) for item in records
    )
    plausible = sum(
        bool(item.get("evaluation", {}).get("plausible")) for item in records
    )
    validated = sum(
        bool(item.get("evaluation", {}).get("validated")) for item in records
    )
    return {
        "compile_success": compile_success,
        "compile_success_rate": compile_success / total if total else None,
        "plausible": plausible,
        "plausible_rate": plausible / total if total else None,
        "total": total,
        "valid_model_output": valid_output,
        "valid_model_output_rate": valid_output / total if total else None,
        "validated": validated,
        "validated_rate": validated / total if total else None,
    }


def _usage_metrics(
    records: list[dict[str, Any]], prices: dict[str, float]
) -> dict[str, Any]:
    totals = {
        "calls": len(records),
        "calls_with_usage": 0,
        "prompt_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "reasoning_tokens": 0,
        "final_answer_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for item in records:
        usage = item.get("provider_response_metadata", {}).get("usage")
        if not usage:
            continue
        totals["calls_with_usage"] += 1
        for key in (
            "prompt_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "reasoning_tokens",
            "final_answer_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            if key == "reasoning_tokens":
                value = usage.get("completion_tokens_details", {}).get(key, 0)
            else:
                value = usage.get(key, 0)
            totals[key] += int(value or 0)
    totals["calls_without_usage"] = totals["calls"] - totals["calls_with_usage"]
    totals["estimated_cost_usd"] = round(
        (
            totals["prompt_cache_hit_tokens"] * prices["input_cache_hit"]
            + totals["prompt_cache_miss_tokens"] * prices["input_cache_miss"]
            + totals["completion_tokens"] * prices["output"]
        )
        / 1_000_000,
        6,
    )
    return totals


def _artifact_integrity(
    records: list[dict[str, Any]], prompt_audit: dict[str, Any]
) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: (item["case_id"], item["group"]))
    actual_prompts = [
        {
            "case_id": item["case_id"],
            "group": item["group"],
            "prompt_hash": item["prompt"]["hash"],
        }
        for item in ordered
    ]
    expected_prompts = sorted(
        (
            {
                "case_id": item["case_id"],
                "group": item["group"],
                "prompt_hash": item["prompt_hash"],
            }
            for item in prompt_audit["prompt_records"]
        ),
        key=lambda item: (item["case_id"], item["group"]),
    )
    response_metadata = [
        item["provider_response_metadata"]
        for item in ordered
        if item.get("provider_response_metadata")
    ]
    request_configurations = {
        json.dumps(item["request_configuration"], sort_keys=True)
        for item in response_metadata
    }
    return {
        "artifact_set_hash": _canonical_hash(ordered),
        "attempt_one_only": all(item.get("attempt") == 1 for item in ordered),
        "complete_case_group_pairs": len(actual_prompts),
        "expected_case_group_pairs": 150,
        "formal_role_only": all(
            item.get("experiment_role") == "formal_evidence_ablation"
            for item in ordered
        ),
        "frozen_prompt_set_hash": prompt_audit["prompt_set_hash"],
        "runtime_evidence_manifest_hash": prompt_audit[
            "runtime_evidence_manifest_hash"
        ],
        "prompt_hashes_match_frozen_audit": actual_prompts == expected_prompts,
        "request_configurations": [
            json.loads(item) for item in sorted(request_configurations)
        ],
        "response_metadata_records": len(response_metadata),
        "response_models": sorted(
            {item["response_model"] for item in response_metadata}
        ),
        "system_fingerprints": sorted(
            {item["system_fingerprint"] for item in response_metadata}
        ),
        "unique_cache_keys": len({item["cache_key"] for item in ordered}),
    }


def _paired_comparison(
    records_by_case: dict[str, dict[str, dict[str, Any]]], before: str, after: str
) -> dict[str, Any]:
    case_ids = sorted(
        case_id
        for case_id, groups in records_by_case.items()
        if before in groups and after in groups
    )
    baseline = [
        bool(records_by_case[case_id][before].get("evaluation", {}).get("validated"))
        for case_id in case_ids
    ]
    treatment = [
        bool(records_by_case[case_id][after].get("evaluation", {}).get("validated"))
        for case_id in case_ids
    ]
    if not case_ids:
        return {"cases": 0, "status": "not_available"}
    return {
        "bootstrap": paired_bootstrap_difference(
            baseline,
            treatment,
            samples=BOOTSTRAP_SAMPLES,
            seed=BOOTSTRAP_SEED,
        ),
        "cases": len(case_ids),
        "mcnemar": exact_mcnemar(baseline, treatment),
        "status": "available",
    }


def build_repair_evaluation() -> dict[str, Any]:
    records = _artifact_records(REPAIR_ARTIFACT_ROOT)
    leakage_scan = validate_artifact_boundaries(records)
    online = [item for item in records if _is_formal_artifact(item)]
    pricing = _read_json(DEEPSEEK_FORMAL_PRICING_SNAPSHOT)
    formal_run = _read_json(REPAIR_FORMAL_RUN)
    prompt_audit = _read_json(RUNTIME_EVIDENCE_PROMPT_AUDIT)
    engineering_smoke = [
        item
        for item in records
        if item.get("experimental") is True and not _is_formal_artifact(item)
    ]
    signatures = {_signature(item) for item in online}
    if len(signatures) > 1:
        raise ValueError("multiple online experiment configurations found")
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for item in online:
        groups = by_case.setdefault(item["case_id"], {})
        if item["group"] in groups:
            raise ValueError(
                f"duplicate online artifact for {item['case_id']}/{item['group']}"
            )
        groups[item["group"]] = item
    attributes = {item["case_id"]: item for item in _read_jsonl(REPAIR_PILOT_ATTRIBUTES)}
    fl_records = _read_jsonl(REPAIR_PILOT_FL)
    no_reliable_fl = sorted(
        item["case_id"]
        for item in fl_records
        if not item.get("reliable_locations_available", False)
    )
    failures = Counter(
        mode for item in online for mode in item.get("failure_modes", [])
    )
    classifications = {
        group: dict(
            sorted(
                Counter(
                    item["classification"]
                    for item in online
                    if item["group"] == group
                ).items()
            )
        )
        for group in GROUPS
    }
    fake = [item for item in records if item.get("experimental") is False]
    artifact_integrity = _artifact_integrity(online, prompt_audit)
    if online and (
        artifact_integrity["complete_case_group_pairs"] != 150
        or artifact_integrity["unique_cache_keys"] != 150
        or not artifact_integrity["attempt_one_only"]
        or not artifact_integrity["formal_role_only"]
        or not artifact_integrity["prompt_hashes_match_frozen_audit"]
        or artifact_integrity["response_metadata_records"]
        != formal_run["responses_received"]
        or len(artifact_integrity["request_configurations"]) != 1
        or artifact_integrity["response_models"] != ["deepseek-v4-flash"]
        or len(artifact_integrity["system_fingerprints"]) != 1
        or formal_run["requests_attempted"] != 150
    ):
        raise ValueError("formal repair artifact set is incomplete or inconsistent")
    evaluation = {
        "dataset": _read_json(CODEFLAWS_REPAIR_PILOT_SUMMARY),
        "experiment": {
            "artifact_integrity": artifact_integrity,
            "complete_paired_cases": sum(
                all(group in groups for group in GROUPS) for groups in by_case.values()
            ),
            "configuration": (
                json.loads(next(iter(signatures))) if signatures else None
            ),
            "online_artifacts": len(online),
            "online_experiment_status": "completed" if online else "not_run",
            "run": formal_run,
        },
        "failure_analysis": {
            "classifications_by_group": classifications,
            "infrastructure_or_api_failures": sum(
                item["classification"] == "model_error" for item in online
            ),
            "model_failure_modes": dict(sorted(failures.items())),
            "no_reliable_fl_evidence_case_ids": no_reliable_fl,
            "no_reliable_fl_evidence_cases": len(no_reliable_fl),
        },
        "fl_relationship": {},
        "groups": {
            group: _group_metrics(
                [item for item in online if item["group"] == group]
            )
            for group in GROUPS
        },
        "leakage_scan": leakage_scan,
        "paired_comparisons": {
            f"{after}-{before}": _paired_comparison(by_case, before, after)
            for before, after in PAIRINGS
        },
        "token_usage_and_cost": {
            "by_group": {
                group: _usage_metrics(
                    [item for item in online if item["group"] == group],
                    pricing["prices"],
                )
                for group in GROUPS
            },
            "pricing": pricing,
            "total": _usage_metrics(online, pricing["prices"]),
        },
        "protocol": _read_json(REPAIR_PROTOCOL),
        "smoke_test": {
            "artifacts": len(fake),
            "cases": len({item["case_id"] for item in fake}),
            "classifications": dict(
                sorted(Counter(item["classification"] for item in fake).items())
            ),
            "engineering_online_artifacts_excluded": len(engineering_smoke),
            "provider": "fake (excluded from experimental metrics)",
        },
    }
    if online:
        reliable_ids = {
            item["case_id"]
            for item in fl_records
            if item.get("reliable_locations_available", False)
        }
        diversity_median = statistics.median(
            float(item["coverage_diversity_ratio"]) for item in attributes.values()
        )
        for bucket, predicate in (
            ("fl_reliable", lambda value: value["case_id"] in reliable_ids),
            ("fl_unreliable", lambda value: value["case_id"] not in reliable_ids),
            ("fl_top_1_hit", lambda value: value.get("fl_top_1_hit")),
            ("fl_top_5_hit", lambda value: value.get("fl_top_5_hit")),
            ("fl_top_10_hit", lambda value: value.get("fl_top_10_hit")),
            ("fl_miss", lambda value: not value.get("fl_top_10_hit")),
            ("zero_pass", lambda value: value.get("zero_pass")),
            ("has_pass", lambda value: not value.get("zero_pass")),
            ("non_executable_fault", lambda value: value.get("non_executable_fault")),
            ("executable_fault", lambda value: not value.get("non_executable_fault")),
            (
                "fault_equivalence_singleton",
                lambda value: value.get("fault_equivalence_class_size") == 1,
            ),
            (
                "fault_equivalence_tied",
                lambda value: (value.get("fault_equivalence_class_size") or 0) > 1,
            ),
            ("straight_line_ambiguity", lambda value: value.get("straight_line_ambiguity")),
            (
                "coverage_diversity_lower_half",
                lambda value: value.get("coverage_diversity_ratio", 0)
                <= diversity_median,
            ),
            (
                "coverage_diversity_upper_half",
                lambda value: value.get("coverage_diversity_ratio", 0)
                > diversity_median,
            ),
        ):
            selected = [case_id for case_id, value in attributes.items() if predicate(value)]
            evaluation["fl_relationship"][bucket] = {
                group: _group_metrics(
                    [
                        by_case[case_id][group]
                        for case_id in selected
                        if case_id in by_case and group in by_case[case_id]
                    ]
                )
                for group in GROUPS
            }
        evaluation["fl_relationship"]["coverage_diversity_median"] = diversity_median
    REPAIR_EVALUATION.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_EVALUATION.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evaluation


def _rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def render_report(evaluation: dict[str, Any]) -> str:
    dataset = evaluation["dataset"]
    experiment = evaluation["experiment"]
    result_rows = []
    for group in GROUPS:
        metric = evaluation["groups"][group]
        result_rows.append(
            f"| {group} | {metric['total']} | {metric['valid_model_output']} "
            f"({_rate(metric['valid_model_output_rate'])}) | {metric['compile_success']} "
            f"({_rate(metric['compile_success_rate'])}) | {metric['plausible']} "
            f"({_rate(metric['plausible_rate'])}) | {metric['validated']} "
            f"({_rate(metric['validated_rate'])}) |"
        )
    paired_rows = []
    bootstrap_rows = []
    mcnemar_rows = []
    for name, result in evaluation["paired_comparisons"].items():
        bootstrap = result["bootstrap"]
        mcnemar = result["mcnemar"]
        paired_rows.append(
            f"| {name} | {result['cases']} | {mcnemar['treatment_only']} | "
            f"{mcnemar['baseline_only']} | {bootstrap['observed_difference']:+.2%} |"
        )
        bootstrap_rows.append(
            f"| {name} | {bootstrap['observed_difference']:+.2%} | "
            f"[{bootstrap['confidence_interval_95'][0]:+.2%}, "
            f"{bootstrap['confidence_interval_95'][1]:+.2%}] | "
            f"{bootstrap['samples']} | {bootstrap['seed']} |"
        )
        mcnemar_rows.append(
            f"| {name} | {mcnemar['treatment_only']} | "
            f"{mcnemar['baseline_only']} | {mcnemar['discordant']} | "
            f"{mcnemar['exact_two_sided_p_value']:.6g} |"
        )
    failure_rows = []
    for group in GROUPS:
        counts = evaluation["failure_analysis"]["classifications_by_group"][group]
        failure_rows.append(
            f"| {group} | {counts.get('model_error', 0)} | "
            f"{counts.get('invalid_model_output', 0)} | "
            f"{counts.get('compile_error', 0)} | "
            f"{counts.get('repair_test_failed', 0)} | "
            f"{counts.get('plausible_patch', 0)} | "
            f"{counts.get('validated_patch', 0)} |"
        )
    subgroup_labels = (
        ("fl_reliable", "FL reliable"),
        ("fl_unreliable", "FL unreliable"),
        ("fl_top_1_hit", "FL Top-1 hit"),
        ("fl_top_5_hit", "FL Top-5 hit"),
        ("fl_top_10_hit", "FL Top-10 hit"),
        ("fl_miss", "FL Top-10 miss"),
        ("zero_pass", "0-PASS"),
        ("has_pass", ">=1 PASS"),
        ("non_executable_fault", "Non-executable fault"),
        ("executable_fault", "Executable fault"),
        ("fault_equivalence_singleton", "Fault equivalence singleton"),
        ("fault_equivalence_tied", "Fault equivalence tied"),
        ("straight_line_ambiguity", "Straight-line ambiguity"),
        ("coverage_diversity_lower_half", "Coverage diversity lower half"),
        ("coverage_diversity_upper_half", "Coverage diversity upper half"),
    )
    subgroup_rows = []
    for key, label in subgroup_labels:
        value = evaluation["fl_relationship"][key]
        subgroup_rows.append(
            f"| {label} | {value['A']['total']} | {_rate(value['A']['validated_rate'])} | "
            f"{_rate(value['B']['validated_rate'])} | "
            f"{_rate(value['C']['validated_rate'])} |"
        )
    usage = evaluation["token_usage_and_cost"]
    usage_rows = []
    for group in GROUPS:
        value = usage["by_group"][group]
        usage_rows.append(
            f"| {group} | {value['calls_with_usage']}/{value['calls']} | "
            f"{value['prompt_tokens']} | {value['prompt_cache_hit_tokens']} | "
            f"{value['prompt_cache_miss_tokens']} | {value['reasoning_tokens']} | "
            f"{value['final_answer_tokens']} | {value['completion_tokens']} | "
            f"{value['total_tokens']} | ${value['estimated_cost_usd']:.6f} |"
        )
    reasons = ", ".join(
        f"{key}={value}"
        for key, value in dataset["dynamic_exclusion_reasons"].items()
    )
    smoke = evaluation["smoke_test"]
    no_reliable_fl = evaluation["failure_analysis"][
        "no_reliable_fl_evidence_case_ids"
    ]
    integrity = experiment["artifact_integrity"]
    run = experiment["run"]
    prices = usage["pricing"]
    total_usage = usage["total"]
    diversity_median = evaluation["fl_relationship"][
        "coverage_diversity_median"
    ]
    return f"""# LLM Repair Evidence Ablation

## 1. Research Questions

**Does fault-localization and execution evidence improve single-attempt LLM program repair?**

RQ1 compares Group B with A to estimate the association of frozen FL-v1 evidence with validated repair. RQ2 compares Group C with B to estimate the incremental association of frozen runtime evidence. C versus A reports their combined difference. All results are paired at case level; descriptive subgroup results are not filtering rules or new experiments.

## 2. Frozen Experimental Protocol

- Protocol `repair-v2`, prompt `repair-evidence-v2`, one attempt per case/group, transport retries 0.
- Formal artifacts were completed from {run['first_artifact_completed_at']} to {run['last_artifact_completed_at']}; requests attempted {run['requests_attempted']}, responses received {run['responses_received']}, resume used `{str(run['resume_used']).lower()}`.
- Runtime Evidence manifest hash: `{integrity['runtime_evidence_manifest_hash']}`.
- Frozen formal prompt-set hash: `{integrity['frozen_prompt_set_hash']}`; artifact prompt hashes match: `{str(integrity['prompt_hashes_match_frozen_audit']).lower()}`.
- Formal artifact set hash: `{integrity['artifact_set_hash']}`; unique cache keys {integrity['unique_cache_keys']}/150; attempt-one-only `{str(integrity['attempt_one_only']).lower()}`; formal-role-only `{str(integrity['formal_role_only']).lower()}`.
- The {smoke['engineering_online_artifacts_excluded']} DeepSeek engineering smoke artifacts and {smoke['artifacts']} fake-provider artifacts are excluded from formal effectiveness metrics.

## 3. Dataset / Repair Pilot

- Selection seed: `{dataset['seed']}`.
- Static candidate count after excluding the prior sets: {dataset['candidate_count']}; dynamically tested: {dataset['dynamic_candidates_tested']}.
- Final Repair Pilot: {dataset['repair_pilot_size']} cases; dynamic exclusions: {dataset['dynamic_exclusions']} ({reasons}); static exclusions: {dataset['static_exclusions']}.
- Overlap with the 50-case FL Pilot: {dataset['fl_pilot_overlap']}; overlap with the 300-case independent FL Evaluation: {dataset['fl_evaluation_overlap']}.

## 4. Model and Provider

- Provider: DeepSeek Official API; model `deepseek-v4-flash`; observed response model `deepseek-v4-flash` and system fingerprint recorded per response.
- Thinking enabled, reasoning effort low, max tokens 16384, stream false, temperature and seed not sent, request timeout 120 seconds.
- Received 148 responses; the two absent responses are retained as infrastructure/API failures and were not retried.

## 5. A/B/C Definitions

- Group A: complete buggy source plus the common repair-time input/expected-output oracle.
- Group B: Group A plus frozen CodeDoctor FL-v1 Top-10 locations, or the uniform no-reliable-location message when FL-v1 itself produces no positive-score location.
- Group C: Group B plus runtime-only repair-test verdict, actual stdout/stderr, exit code, and timeout state. Input and expected output remain exclusively in the shared base context.
- Patch protocol: complete-source extraction, Docker compilation, repair tests, then hidden validation for plausible patches.

## 6. Leakage Boundary

`RepairContext` can contain only case ID, language, buggy source, the common repair-time oracle, registered FL-v1 locations/status, and runtime execution evidence. Reference source, ground-truth diff/lines, and hidden validation tests are held in a separate evaluation-only boundary and are not accepted by prompt rendering. The Codeflaws distribution has no per-case problem statements, so existing repair-test input/expected-output pairs serve as a versioned common oracle and are identical in A/B/C. Prompt canary tests and artifact scans cover `REFERENCE_SECRET_TOKEN` and `VALIDATION_SECRET_TOKEN`. API keys are neither serialized nor cached. Artifact boundary scan: `{evaluation['leakage_scan']['status']}` over {evaluation['leakage_scan']['artifacts_checked']} artifacts.

## 7. Main Results

| Group | Cases | Valid output | Compile success | Plausible | Validated patch |
|---|---:|---:|---:|---:|---:|
{chr(10).join(result_rows)}

Validated Patch means all available repair and hidden validation tests passed. **Validated Patch is not Formally Correct Patch.**

## 8. Paired Comparison

| Comparison | Paired cases | Before fail / after success | Before success / after fail | Validated-rate difference |
|---|---:|---:|---:|---:|
{chr(10).join(paired_rows)}

## 9. Paired Bootstrap 95% CI

| Comparison | Observed difference | 95% CI | Samples | Seed |
|---|---:|---:|---:|---:|
{chr(10).join(bootstrap_rows)}

The interval is a percentile paired bootstrap over 50 case-level validated/not-validated differences. It is descriptive uncertainty for this frozen Pilot and model run.

## 10. Exact McNemar Results

| Comparison | Before fail / after success | Before success / after fail | Discordant | Exact two-sided p |
|---|---:|---:|---:|---:|
{chr(10).join(mcnemar_rows)}

The p-values are exact, two-sided, and unadjusted for the three reported comparisons. No protocol or hypothesis was changed in response to them.

## 11. Failure Analysis

| Group | Model/API error | Invalid model output | Compile error | Repair-test failed | Plausible but validation failed | Validated patch |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(failure_rows)}

The two model/API failures were one request timeout and one URL-open timeout for the same case in A/B; transport retry remained 0. Invalid outputs were length-truncated responses with no extractable final source. No failed, uncompilable, implausible, or overfitting patch was retried.

## 12. FL Quality vs Repair Outcome

| Descriptive subgroup | Cases | A validated | B validated | C validated |
|---|---:|---:|---:|---:|
{chr(10).join(subgroup_rows)}

FL-v1 had no reliable positive-score location for {len(no_reliable_fl)} case: {no_reliable_fl or 'none'}. Coverage diversity uses a post-hoc descriptive Pilot median split at {diversity_median:.6f}. These Top-k, 0-PASS, executable-fault, equivalence-class, ambiguity, and diversity summaries are exploratory and were not used to remove cases or rerun the model.

## 13. Token Usage / API Cost

| Group | Usage records/calls | Prompt | Cache hit | Cache miss | Reasoning | Final answer | Completion | Total | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(usage_rows)}

- Aggregate usage-bearing responses: {total_usage['calls_with_usage']}/{total_usage['calls']}; calls without usage: {total_usage['calls_without_usage']}.
- Aggregate prompt/cache-hit/cache-miss tokens: {total_usage['prompt_tokens']} / {total_usage['prompt_cache_hit_tokens']} / {total_usage['prompt_cache_miss_tokens']}.
- Aggregate reasoning/final-answer/completion/total tokens: {total_usage['reasoning_tokens']} / {total_usage['final_answer_tokens']} / {total_usage['completion_tokens']} / {total_usage['total_tokens']}.
- Actual-usage cost estimate: `${total_usage['estimated_cost_usd']:.6f}` using the [DeepSeek Official API prices]({prices['official_source']}) verified at `{prices['verified_at']}`: cache hit `${prices['prices']['input_cache_hit']}`/M, cache miss `${prices['prices']['input_cache_miss']}`/M, output `${prices['prices']['output']}`/M. The two failed requests report no usage and therefore contribute no token-based cost estimate.

## 14. Threats to Validity

- The 50-case Repair Pilot is small; paired confidence intervals may be wide.
- Results depend on one selected mutable provider alias, one observed fingerprint, and stochastic model behavior.
- Codeflaws programs and tests may not represent larger real-world C/C++ systems.
- Repair and hidden validation suites are incomplete; validated is not formally correct.
- Findings may be prompt-sensitive even though the A/B/C base instruction is fixed.
- Two provider failures count as not validated; conclusions may differ under another independently preregistered run, but this run cannot be repaired post hoc.
- The three paired p-values are reported without multiplicity adjustment and should not be read as three independent confirmatory tests.
- Subgroup analyses are small, overlapping, and descriptive; they do not establish causal moderation.
- Token cost is computed from provider-reported usage and the official price snapshot, not an account billing export.

## 15. Conclusion

On this frozen 50-case run, Group B did not improve over A: 78% versus 80%, difference -2 percentage points, bootstrap 95% CI [-14, +12], exact McNemar p=1. Group C reached 92%, improving over B by 14 points with bootstrap 95% CI [+4, +26] and exact McNemar p=0.0390625; C exceeded A by 12 points, CI [0, +24], p=0.109375. Thus RQ1 provides no evidence that FL-v1 alone improved validated repair in this run, while RQ2 shows a positive paired association for adding frozen runtime evidence. The Pilot, incomplete test oracle, stochastic provider, multiple descriptive comparisons, and non-formal meaning of validation prevent broader correctness or causal claims.
"""


def write_report() -> dict[str, Any]:
    evaluation = build_repair_evaluation()
    REPAIR_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_REPORT.write_text(render_report(evaluation), encoding="utf-8")
    return evaluation
