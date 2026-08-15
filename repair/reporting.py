"""Aggregate online repair artifacts and render the evidence-ablation report."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT_SUMMARY,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_EVALUATION,
    REPAIR_PILOT_ATTRIBUTES,
    REPAIR_PROTOCOL,
    REPAIR_REPORT,
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
        for path in sorted(root.glob("*/*/*.json"))
    ]


def _signature(record: dict[str, Any]) -> str:
    value = {
        "model_parameters": record["model_parameters"],
        "template_version": record["prompt"]["template_version"],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_artifact_boundaries(records: list[dict[str, Any]]) -> dict[str, Any]:
    violations = []
    for item in records:
        prompt = item.get("prompt", {})
        text = str(prompt.get("system", "")) + str(prompt.get("user", ""))
        group = item.get("group")
        if any(canary in text for canary in LEAKAGE_CANARIES):
            violations.append(f"{item.get('case_id')}/{group}: evaluation canary")
        has_fl = "## CodeDoctor FL-v1 suspicious locations" in text
        has_execution = "## Repair-test execution evidence" in text
        if group == "A" and (has_fl or has_execution):
            violations.append(f"{item.get('case_id')}/A: extra evidence")
        elif group == "B" and (not has_fl or has_execution):
            violations.append(f"{item.get('case_id')}/B: evidence boundary")
        elif group == "C" and (not has_fl or not has_execution):
            violations.append(f"{item.get('case_id')}/C: evidence boundary")
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
    online = [item for item in records if item.get("experimental") is True]
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
    failures = Counter(
        mode for item in online for mode in item.get("failure_modes", [])
    )
    fake = [item for item in records if item.get("experimental") is False]
    evaluation = {
        "dataset": _read_json(CODEFLAWS_REPAIR_PILOT_SUMMARY),
        "experiment": {
            "complete_paired_cases": sum(
                all(group in groups for group in GROUPS) for groups in by_case.values()
            ),
            "configuration": (
                json.loads(next(iter(signatures))) if signatures else None
            ),
            "online_artifacts": len(online),
            "online_experiment_status": "completed" if online else "not_run_no_credentials",
        },
        "failure_analysis": dict(sorted(failures.items())),
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
        "protocol": _read_json(REPAIR_PROTOCOL),
        "smoke_test": {
            "artifacts": len(fake),
            "cases": len({item["case_id"] for item in fake}),
            "classifications": dict(
                sorted(Counter(item["classification"] for item in fake).items())
            ),
            "provider": "fake (excluded from experimental metrics)",
        },
    }
    if online:
        for bucket, predicate in (
            ("fl_top_1_hit", lambda value: value.get("fl_top_1_hit")),
            ("fl_top_5_hit", lambda value: value.get("fl_top_5_hit")),
            ("fl_top_10_hit", lambda value: value.get("fl_top_10_hit")),
            ("fl_miss", lambda value: not value.get("fl_top_10_hit")),
            ("zero_pass", lambda value: value.get("zero_pass")),
            ("has_pass", lambda value: not value.get("zero_pass")),
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
    rows = []
    for group in GROUPS:
        metric = evaluation["groups"][group]
        rows.append(
            f"| {group} | {metric['total']} | {_rate(metric['valid_model_output_rate'])} | "
            f"{_rate(metric['compile_success_rate'])} | {_rate(metric['plausible_rate'])} | "
            f"{_rate(metric['validated_rate'])} |"
        )
    pair_rows = []
    for name, result in evaluation["paired_comparisons"].items():
        if result["status"] == "not_available":
            pair_rows.append(f"| {name} | 0 | N/A | N/A | N/A | N/A |")
        else:
            bootstrap = result["bootstrap"]
            mcnemar = result["mcnemar"]
            pair_rows.append(
                f"| {name} | {result['cases']} | {bootstrap['observed_difference']:+.2%} | "
                f"[{bootstrap['confidence_interval_95'][0]:+.2%}, "
                f"{bootstrap['confidence_interval_95'][1]:+.2%}] | "
                f"{mcnemar['treatment_only']}/{mcnemar['baseline_only']} | "
                f"{mcnemar['exact_two_sided_p_value']:.6g} |"
            )
    reasons = ", ".join(
        f"{key}={value}"
        for key, value in dataset["dynamic_exclusion_reasons"].items()
    )
    smoke = evaluation["smoke_test"]
    return f"""# LLM Repair Evidence Ablation

## 1. Research Question

**Does fault-localization and execution evidence improve single-attempt LLM program repair?**

This report preregisters and implements the experiment, but the current environment had no API credential, base URL, or online model configured. Therefore no online A/B/C effectiveness result is claimed. Fake-provider smoke artifacts are explicitly excluded from all experimental metrics.

## 2. Dataset

- Selection seed: `{dataset['seed']}`.
- Static candidate count after excluding the prior sets: {dataset['candidate_count']}; dynamically tested: {dataset['dynamic_candidates_tested']}.
- Final Repair Pilot: {dataset['repair_pilot_size']} cases; dynamic exclusions: {dataset['dynamic_exclusions']} ({reasons}); static exclusions: {dataset['static_exclusions']}.
- Overlap with the 50-case FL Pilot: {dataset['fl_pilot_overlap']}; overlap with the 300-case independent FL Evaluation: {dataset['fl_evaluation_overlap']}.

## 3. Experimental Setup

- Protocol: `repair-v1`; prompt: `repair-evidence-v1`; one attempt per case/group.
- Group A: complete buggy source and the common repair instruction only.
- Group B: Group A plus frozen CodeDoctor FL-v1 Top-10 locations.
- Group C: Group B plus repair-test PASS/FAIL, input, expected output, actual stdout/stderr, exit code, and timeout state.
- Registered defaults: temperature 0.0, maximum output tokens 4096, request timeout 120 seconds. A seed is sent only when explicitly configured and supported; determinism is not assumed.
- Model/version: not configured; online calls: {experiment['online_artifacts']}.
- Patch protocol: complete source extraction, Docker compilation, repair tests, then hidden validation for plausible patches. A validated patch means that all available repair and hidden validation tests pass; it is not formal correctness.

## 4. Leakage Boundary

`RepairContext` can contain only case ID, language, buggy source, registered FL-v1 locations, and repair-test execution evidence. Reference source, ground-truth diff/lines, and hidden validation tests are held in a separate evaluation-only boundary and are not accepted by prompt rendering. Prompt canary tests and artifact scans cover `REFERENCE_SECRET_TOKEN` and `VALIDATION_SECRET_TOKEN`. API keys are neither serialized nor cached. Artifact boundary scan: `{evaluation['leakage_scan']['status']}` over {evaluation['leakage_scan']['artifacts_checked']} artifacts.

## 5. Results

| Group | Cases | Valid output | Compile success | Plausible | Validated |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

| Comparison | Paired cases | Validated-rate difference | Bootstrap 95% CI | After-only/Before-only | Exact McNemar p |
|---|---:|---:|---:|---:|---:|
{chr(10).join(pair_rows)}

Online experiment status: `{experiment['online_experiment_status']}`. These N/A cells are intentional and must not be replaced with fake-provider outcomes.

## 6. Failure Analysis

No online model failures are available for scientific analysis. The local fake-provider smoke ran {smoke['artifacts']} artifacts over {smoke['cases']} cases across A/B/C; classifications were {smoke['classifications']}. The fake returned the buggy source unchanged, so this confirms context, extraction, Docker compilation, repair-test classification, artifact writing, and resume boundaries without estimating repair ability. A separate non-artifact evaluator check ran one reference source through repair plus hidden validation and reached `validated_patch`.

The implemented online analysis distinguishes invalid output, compile error, still failing original failing tests, regression on previously passing repair tests, and validation overfitting. It also records line-diff size, whether an FL Top-10 line was modified, FL Top-1/5/10 hit strata, 0-PASS, non-executable fault, equivalence-class size, and coverage diversity.

## 7. Threats to Validity

- The 50-case Repair Pilot is small; paired confidence intervals may be wide.
- Results will depend on one selected LLM/model version and its stochastic behavior.
- Temperature zero and an optional seed do not guarantee provider determinism.
- Codeflaws programs and tests may not represent larger real-world C/C++ systems.
- Repair and hidden validation suites are incomplete; validated is not formally correct.
- Findings may be prompt-sensitive even though the A/B/C base instruction is fixed.
- No online credential was available in this run, so the core causal comparison remains unmeasured.

## 8. Conclusion

Phase 7 establishes a disjoint Repair Pilot, a frozen single-attempt protocol, auditable A/B/C prompts, strict leakage boundaries, content-addressed resume, Docker patch validation, paired statistics, and reporting. It does **not** yet answer whether FL or execution evidence improves LLM repair because no genuine online model call was possible. The next valid operation is to configure one fixed OpenAI-compatible model and run a small genuine smoke before the full 50-case A/B/C experiment without changing this protocol after observing outcomes.
"""


def write_report() -> dict[str, Any]:
    evaluation = build_repair_evaluation()
    REPAIR_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_REPORT.write_text(render_report(evaluation), encoding="utf-8")
    return evaluation
