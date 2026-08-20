"""Build thesis-facing tables and registries from frozen Phase 4-9 artifacts."""

import csv
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

from benchmark.config import (
    CODEFLAWS_FL_EVALUATION,
    CODEFLAWS_PILOT,
    CODEFLAWS_REPAIR_PILOT,
    FINAL_AUDIT_SUMMARY,
    FINAL_DATASET_OVERLAP,
    FINAL_EXPERIMENT_REGISTRY,
    FINAL_FREEZE,
    FINAL_METADATA_ROOT,
    FINAL_REPORT_TABLE_ROOT,
    FINAL_REPRODUCIBILITY_REGISTRY,
    FINAL_RESEARCH_SUMMARY,
    FAULT_LOCALIZATION_BRANCH_EVALUATION,
    FAULT_LOCALIZATION_EVALUATION,
    FAULT_LOCALIZATION_INDEPENDENT_EVALUATION,
    FAULT_LOCALIZATION_INDEPENDENT_REPORT,
    FAULT_LOCALIZATION_REPORT,
    PHASE8_ELIGIBLE_COHORT,
    PHASE8_EVALUATION_SET,
    PHASE8_FINAL_REPORT,
    PHASE8_STAGE1_MANIFEST,
    PHASE8_STAGE1_REPORT,
    PHASE8_STAGE2_RESULT_MANIFEST,
    PHASE9_DIFFERENTIAL_MANIFEST,
    PHASE9_PATCH_CORPUS,
    PHASE9_REPORT,
    PHASE9_RESULT_MANIFEST,
    PROJECT_ROOT,
    REPAIR_EVALUATION,
    REPAIR_FORMAL_RUN,
    REPAIR_REPORT,
)
from repair_phase8.partition import canonical_hash


SOURCE_COMMIT = "378c8520ddbc0508f5b40fc14f605c7393b5366e"
DATASETS = {
    "FL Pilot": (CODEFLAWS_PILOT, 50, 20260815),
    "Independent FL Evaluation": (CODEFLAWS_FL_EVALUATION, 300, 20260816),
    "Phase 7 Repair Pilot": (CODEFLAWS_REPAIR_PILOT, 50, 20260817),
    "Phase 8 Repair Evaluation": (PHASE8_EVALUATION_SET, 100, 20260820),
}
INTRODUCTION_COMMITS = {
    "phase4": "f2a85a820079c9abef084d48133943e0e3b1c7a2",
    "phase5": "768bd26e92de45c22d4652e31afc04ce8caa6632",
    "phase6": "76b57e049a57fe691859c79685febc025daf6e61",
    "phase7": "8c90a30c7ea1c47012eeb8a8e95c0b76565ed43e",
    "phase8_stage1": "223baa6c2094f331d7cefdddc7a032db7714b257",
    "phase8_stage2": "b43dcca8bc1921ef7b55450439fb2c9b0920bea0",
    "phase9": SOURCE_COMMIT,
}
EXPECTED_HASHES = {
    "phase4_evaluation_file": "d97e9e1060d3a5e2ec72f2158bf7de084595946815fb9bb32e4c7d666a7cd349",
    "phase5_evaluation_file": "38a38602c8c4c8fbf81920062c8cc8435aec3b75cb3d545ab161525fb15f6a9c",
    "phase6_evaluation_file": "5fef7b3589af6756a32e11ee7d083c8ed6691a126ff62ebf86c9765f4c09c2f2",
    "phase7_artifact_set": "067710f9f3b71855cc4bf1db3dd0614cef89c1d4cec7e4f6e83c0372b7607f17",
    "phase8_stage1": "7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b",
    "phase8_cohort": "e1ec70b962cda0754c336896cd0975d2ef9794d410146c34223d50792797c9c5",
    "phase8_stage2_artifacts": "cf4f44f802913085ce70d7da344a3952c014295f712954b0de93d58ab2c96a04",
    "phase8_stage2_result": "bdc07d0be135edfc51e9c16c48c6163cead0cee6762654a30e0b76a483e4f95e",
    "phase9_corpus": "365902f86f92987d25d5ba9c8167a21b776c57b83ee7025a4ecd11a055eeffd9",
    "phase9_differential": "f593f20b0af854a63d7b8ca3caf41a6734080b1fd7f0cad5fc5e82e0886a7682",
    "phase9_result": "48341fd5925b381124bb3cca3e93b3d1f59ff092dcc298edf933761ee34b5e38",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ValueError(f"final consolidation discrepancy for {label}: {actual!r} != {expected!r}")


def _assert_close(label: str, actual: float, expected: float, tolerance: float = 0.00005) -> None:
    if abs(actual - expected) > tolerance:
        raise ValueError(f"final consolidation discrepancy for {label}: {actual!r} != {expected!r}")


def _self_hash(value: dict[str, Any]) -> str:
    claimed = value.get("overall_manifest_hash")
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    if claimed != canonical_hash(unsigned):
        raise ValueError("self-hashed frozen manifest failed verification")
    return str(claimed)


def _report_number(path: Path, pattern: str, converter: Any = int) -> Any:
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"expected metric absent from formal report: {path}: {pattern}")
    return converter(match.group(1))


def load_frozen_sources() -> dict[str, Any]:
    values = {
        "fl4": _load(FAULT_LOCALIZATION_EVALUATION),
        "fl5": _load(FAULT_LOCALIZATION_BRANCH_EVALUATION),
        "fl6": _load(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION),
        "phase7": _load(REPAIR_EVALUATION),
        "phase7_run": _load(REPAIR_FORMAL_RUN),
        "phase8_stage1": _load(PHASE8_STAGE1_MANIFEST),
        "phase8_cohort": _load(PHASE8_ELIGIBLE_COHORT),
        "phase8_stage2": _load(PHASE8_STAGE2_RESULT_MANIFEST),
        "phase9_corpus": _load(PHASE9_PATCH_CORPUS),
        "phase9_differential": _load(PHASE9_DIFFERENTIAL_MANIFEST),
        "phase9": _load(PHASE9_RESULT_MANIFEST),
    }
    for key in (
        "phase8_stage1",
        "phase8_cohort",
        "phase8_stage2",
        "phase9_corpus",
        "phase9_differential",
        "phase9",
    ):
        _self_hash(values[key])
    return values


def validate_frozen_metrics(v: dict[str, Any]) -> None:
    original = v["fl6"]["metrics"]["ochiai"]
    treatment = v["fl6"]["metrics"]["ochiai_branch_tiebreak"]
    for label, actual, expected in (
        ("FL6 original Top-1", original["top_1_accuracy"], 0.1233),
        ("FL6 original Top-3", original["top_3_accuracy"], 0.3033),
        ("FL6 original Top-5", original["top_5_accuracy"], 0.44),
        ("FL6 original Top-10", original["top_10_accuracy"], 0.6867),
        ("FL6 original MRR", original["mrr"], 0.2773),
        ("FL6 original average MRR", original["tie_aware"]["average_rank"]["mrr"], 0.2552),
        ("FL6 original pessimistic MRR", original["tie_aware"]["pessimistic"]["mrr"], 0.1880),
        ("FL6 FL-v1 Top-1", treatment["top_1_accuracy"], 0.1833),
        ("FL6 FL-v1 Top-3", treatment["top_3_accuracy"], 0.4),
        ("FL6 FL-v1 Top-5", treatment["top_5_accuracy"], 0.5233),
        ("FL6 FL-v1 Top-10", treatment["top_10_accuracy"], 0.7233),
        ("FL6 FL-v1 MRR", treatment["mrr"], 0.3475),
        ("FL6 FL-v1 average MRR", treatment["tie_aware"]["average_rank"]["mrr"], 0.3456),
        ("FL6 FL-v1 pessimistic MRR", treatment["tie_aware"]["pessimistic"]["mrr"], 0.3004),
    ):
        _assert_close(label, actual, expected)
    bootstrap = v["fl6"]["bootstrap"]
    _assert_close("FL6 deterministic delta", bootstrap["deterministic_mrr_difference"]["observed_difference"], 0.0702)
    _assert_close("FL6 average delta", bootstrap["average_rank_mrr_difference"]["observed_difference"], 0.0904)
    for key, expected in (
        ("cases_with_top_score_tie", (231, 157)),
        ("cases_with_fault_line_tied", (256, 205)),
        ("average_max_tie_size", (15.87, 11.84)),
        ("average_fault_tie_size", (12.05, 6.44)),
    ):
        left = v["fl6"]["tie_statistics"]["ochiai"][key]
        right = v["fl6"]["tie_statistics"]["ochiai_branch_tiebreak"][key]
        if isinstance(expected[0], int):
            _assert_equal(f"FL6 tie {key}", (left, right), expected)
        else:
            _assert_close(f"FL6 tie original {key}", left, expected[0], 0.005)
            _assert_close(f"FL6 tie FL-v1 {key}", right, expected[1], 0.005)

    for arm, expected in {"A": 40, "B": 39, "C": 46}.items():
        _assert_equal(f"Phase7 {arm} validated", v["phase7"]["groups"][arm]["validated"], expected)
    paired = v["phase7"]["paired_comparisons"]
    for key, expected in {
        "B-A": (5, 6, -0.02, [-0.14, 0.12], 1.0),
        "C-B": (8, 1, 0.14, [0.04, 0.26], 0.0390625),
        "C-A": (8, 2, 0.12, [0.0, 0.24], 0.109375),
    }.items():
        item = paired[key]
        actual = (
            item["mcnemar"]["treatment_only"],
            item["mcnemar"]["baseline_only"],
            item["bootstrap"]["observed_difference"],
            item["bootstrap"]["confidence_interval_95"],
            item["mcnemar"]["exact_two_sided_p_value"],
        )
        _assert_equal(f"Phase7 paired {key}", actual, expected)
    _assert_equal("Phase7 attempted", v["phase7_run"]["requests_attempted"], 150)
    _assert_equal("Phase7 received", v["phase7_run"]["responses_received"], 148)

    reasons = [item["eligibility_reason"] for item in v["phase8_stage1"]["entries"]]
    _assert_equal("Phase8 Stage1 count", len(reasons), 100)
    _assert_equal("Phase8 Stage1 valid", sum(item["first_patch_hash"] is not None for item in v["phase8_stage1"]["entries"]), 91)
    _assert_equal("Phase8 Stage1 repair success", reasons.count("repair_time_success"), 85)
    _assert_equal("Phase8 eligible", v["phase8_cohort"]["eligible_count"], 6)
    stage2 = v["phase8_stage2"]
    _assert_equal("Phase8 Stage2 calls", stage2["calls"], {"attempted": 12, "provider_failures": 0, "received": 12})
    _assert_equal("Phase8 Stage2 paired", tuple(stage2["paired"][key] for key in ("both_success", "retry_fail_feedback_success", "retry_success_feedback_fail", "both_fail")), (3, 1, 1, 1))
    _assert_equal("Phase8 R/F validated", (stage2["paired"]["retry_validated"], stage2["paired"]["feedback_validated"]), (4, 4))

    phase9 = v["phase9"]
    _assert_equal("Phase9 corpus", (phase9["patch_count"], phase9["unique_case_count"]), (245, 141))
    _assert_equal("Phase9 ladder", tuple(phase9["metrics"][key] for key in ("V1_plausible", "V2_existing_validated", "V2_to_V3_rejections", "V2_to_V4_rejections", "strongly_validated")), (229, 218, 0, 52, 149))
    _assert_equal("Phase9 differential", (phase9["differential"]["candidate_count"], phase9["differential"]["accepted_test_count"], phase9["differential"]["zero_accepted_case_count"]), (50911, 11983, 13))
    _assert_equal("Phase9 failure modes", phase9["failure_modes"]["affected_patch_counts"], {"differential_output_mismatch": 50, "differential_timeout": 2})


def build_dataset_audit() -> dict[str, Any]:
    records = []
    case_sets: dict[str, set[str]] = {}
    for name, (path, expected_count, seed) in DATASETS.items():
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        case_ids = {item["case_id"] for item in rows}
        _assert_equal(f"{name} manifest rows", len(rows), expected_count)
        _assert_equal(f"{name} unique cases", len(case_ids), expected_count)
        case_sets[name] = case_ids
        records.append(
            {
                "case_count": len(case_ids),
                "dataset": name,
                "manifest_path": _relative(path),
                "manifest_sha256": _sha256(path),
                "random_seed": seed,
            }
        )
    matrix = []
    for left in DATASETS:
        row = {"dataset": left}
        for right in DATASETS:
            row[right] = len(case_sets[left] & case_sets[right])
        matrix.append(row)
    cross_overlaps = [
        len(case_sets[left] & case_sets[right])
        for index, left in enumerate(DATASETS)
        for right in list(DATASETS)[index + 1 :]
    ]
    _assert_equal("formal dataset cross-overlap", cross_overlaps, [0] * 6)
    value: dict[str, Any] = {
        "datasets": records,
        "matrix": matrix,
        "protocol_version": "final-dataset-overlap-v1",
        "status": "passed",
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def _metric_row(experiment: str, method: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment": experiment,
        "method": method,
        "cases": metrics["evaluated_cases"],
        "top_1": metrics["top_1_accuracy"],
        "top_3": metrics["top_3_accuracy"],
        "top_5": metrics["top_5_accuracy"],
        "top_10": metrics["top_10_accuracy"],
        "mrr": metrics["mrr"],
        "average_rank_mrr": metrics["tie_aware"]["average_rank"]["mrr"],
        "pessimistic_mrr": metrics["tie_aware"]["pessimistic"]["mrr"],
    }


def _phase7_cost() -> dict[str, Any]:
    tokens = _report_number(REPAIR_REPORT, r"completion/total tokens: \d+ / \d+ / \d+ / (\d+)")
    cost = _report_number(REPAIR_REPORT, r"Actual-usage cost estimate: `\$(\d+\.\d+)`,?", float)
    _assert_equal("Phase7 total tokens", tokens, 894297)
    _assert_close("Phase7 cost", cost, 0.226089, 0.00000001)
    run = _load(REPAIR_FORMAL_RUN)
    return {
        "experiment": "Phase 7 A/B/C",
        "attempted_calls": run["requests_attempted"],
        "successful_responses": run["responses_received"],
        "provider_failures": run["requests_attempted"] - run["responses_received"],
        "total_tokens": tokens,
        "estimated_cost_usd": cost,
    }


def _phase8_stage1_cost() -> dict[str, Any]:
    tokens = _report_number(PHASE8_STAGE1_REPORT, r"completion/total tokens: \d+ / \d+ / \d+ / (\d+)")
    cost = _report_number(PHASE8_STAGE1_REPORT, r"provider-reported usage: `\$(\d+\.\d+)`", float)
    _assert_equal("Phase8 Stage1 total tokens", tokens, 1397722)
    _assert_close("Phase8 Stage1 cost", cost, 0.28257446, 0.000000001)
    return {
        "experiment": "Phase 8 Stage 1 Initial",
        "attempted_calls": 100,
        "successful_responses": 100,
        "provider_failures": 0,
        "total_tokens": tokens,
        "estimated_cost_usd": cost,
    }


def build_cost_rows(v: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_phase7_cost(), _phase8_stage1_cost()]
    stage2 = v["phase8_stage2"]
    rows.append(
        {
            "experiment": "Phase 8 Stage 2 R/F",
            "attempted_calls": stage2["calls"]["attempted"],
            "successful_responses": stage2["calls"]["received"],
            "provider_failures": stage2["calls"]["provider_failures"],
            "total_tokens": stage2["usage_and_cost"]["total"]["tokens"]["total_tokens"],
            "estimated_cost_usd": stage2["usage_and_cost"]["total"]["cost_usd"],
        }
    )
    rows.append(
        {
            "experiment": "Formal LLM experiments total",
            "attempted_calls": sum(item["attempted_calls"] for item in rows),
            "successful_responses": sum(item["successful_responses"] for item in rows),
            "provider_failures": sum(item["provider_failures"] for item in rows),
            "total_tokens": sum(item["total_tokens"] for item in rows),
            "estimated_cost_usd": round(sum(item["estimated_cost_usd"] for item in rows), 8),
        }
    )
    _assert_equal("formal LLM total calls", (rows[-1]["attempted_calls"], rows[-1]["successful_responses"]), (262, 260))
    _assert_equal("formal LLM total tokens", rows[-1]["total_tokens"], 2596824)
    _assert_close("formal LLM total cost", rows[-1]["estimated_cost_usd"], 0.54485862, 0.000000001)
    return rows


def build_table_rows(v: dict[str, Any], datasets: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fl4 = v["fl5"]["metrics"]["ochiai"]
    fl5 = v["fl5"]["metrics"]["ochiai_branch_tiebreak"]
    fl6_original = v["fl6"]["metrics"]["ochiai"]
    fl6_treatment = v["fl6"]["metrics"]["ochiai_branch_tiebreak"]
    fl_rows = [
        _metric_row("Phase 4 FL Pilot", "Original line Ochiai", fl4),
        _metric_row("Phase 5 FL-v1 Pilot", "Branch-aware FL-v1", fl5),
        _metric_row("Phase 6 Independent", "Original line Ochiai", fl6_original),
        _metric_row("Phase 6 Independent", "Branch-aware FL-v1", fl6_treatment),
    ]
    fl_sources = (
        (v["fl5"], "ochiai"),
        (v["fl5"], "ochiai_branch_tiebreak"),
        (v["fl6"], "ochiai"),
        (v["fl6"], "ochiai_branch_tiebreak"),
    )
    for row, (source, method) in zip(fl_rows, fl_sources, strict=True):
        ties = source["tie_statistics"][method]
        row.update(
            {
                "average_rank_mrr": source["metrics"][method]["tie_aware"]["average_rank"]["mrr"],
                "pessimistic_mrr": source["metrics"][method]["tie_aware"]["pessimistic"]["mrr"],
                "top_score_tie_cases": ties["cases_with_top_score_tie"],
                "fault_line_tie_cases": ties["cases_with_fault_line_tied"],
                "average_max_tie_size": ties["average_max_tie_size"],
                "average_fault_tie_size": ties["average_fault_tie_size"],
                "deterministic_mrr_delta": "",
                "deterministic_mrr_ci_95": "",
                "average_rank_mrr_delta": "",
                "average_rank_mrr_ci_95": "",
            }
        )
    fl6_bootstrap = v["fl6"]["bootstrap"]
    fl_rows[-1].update(
        {
            "deterministic_mrr_delta": fl6_bootstrap["deterministic_mrr_difference"]["observed_difference"],
            "deterministic_mrr_ci_95": fl6_bootstrap["deterministic_mrr_difference"]["confidence_interval_95"],
            "average_rank_mrr_delta": fl6_bootstrap["average_rank_mrr_difference"]["observed_difference"],
            "average_rank_mrr_ci_95": fl6_bootstrap["average_rank_mrr_difference"]["confidence_interval_95"],
        }
    )
    phase7 = v["phase7"]
    repair_rows = []
    comparisons = {"A": None, "B": "B-A", "C": "C-B"}
    for arm in ("A", "B", "C"):
        metrics = phase7["groups"][arm]
        comparison = phase7["paired_comparisons"].get(comparisons[arm])
        repair_rows.append(
            {
                "arm": arm,
                "context": {
                    "A": "Base Context",
                    "B": "Base + FL-v1",
                    "C": "Base + FL-v1 + Runtime Evidence",
                }[arm],
                "cases": metrics["total"],
                "valid_output": metrics["valid_model_output"],
                "compile_success": metrics["compile_success"],
                "plausible": metrics["plausible"],
                "validated": metrics["validated"],
                "validated_rate": metrics["validated_rate"],
                "paired_comparison": comparisons[arm] or "",
                "paired_improved": comparison["mcnemar"]["treatment_only"] if comparison else "",
                "paired_regressed": comparison["mcnemar"]["baseline_only"] if comparison else "",
                "paired_difference": comparison["bootstrap"]["observed_difference"] if comparison else "",
                "bootstrap_95_lower": comparison["bootstrap"]["confidence_interval_95"][0] if comparison else "",
                "bootstrap_95_upper": comparison["bootstrap"]["confidence_interval_95"][1] if comparison else "",
                "mcnemar_p": comparison["mcnemar"]["exact_two_sided_p_value"] if comparison else "",
                "secondary_paired_comparison": "C-A" if arm == "C" else "",
                "secondary_paired_improved": phase7["paired_comparisons"]["C-A"]["mcnemar"]["treatment_only"] if arm == "C" else "",
                "secondary_paired_regressed": phase7["paired_comparisons"]["C-A"]["mcnemar"]["baseline_only"] if arm == "C" else "",
                "secondary_paired_difference": phase7["paired_comparisons"]["C-A"]["bootstrap"]["observed_difference"] if arm == "C" else "",
                "secondary_bootstrap_95_lower": phase7["paired_comparisons"]["C-A"]["bootstrap"]["confidence_interval_95"][0] if arm == "C" else "",
                "secondary_bootstrap_95_upper": phase7["paired_comparisons"]["C-A"]["bootstrap"]["confidence_interval_95"][1] if arm == "C" else "",
                "secondary_mcnemar_p": phase7["paired_comparisons"]["C-A"]["mcnemar"]["exact_two_sided_p_value"] if arm == "C" else "",
            }
        )
    stage2 = v["phase8_stage2"]
    end_to_end = stage2["end_to_end"]
    stage1_valid = sum(item["first_patch_hash"] is not None for item in v["phase8_stage1"]["entries"])
    stage1_success = sum(item["eligibility_reason"] == "repair_time_success" for item in v["phase8_stage1"]["entries"])
    feedback_rows = [
        {"scope": "Stage 1", "arm": "Initial", "denominator": len(v["phase8_stage1"]["entries"]), "valid_output": stage1_valid, "compile_success": stage1_valid, "repair_time_success": stage1_success, "invalid_or_length": len(v["phase8_stage1"]["entries"]) - stage1_valid, "validated": end_to_end["S0_initial_only"]["validated"], "validated_rate": end_to_end["S0_initial_only"]["rate"], "both_success": "", "control_fail_treatment_success": "", "control_success_treatment_fail": "", "both_fail": "", "difference": "", "bootstrap_95_lower": "", "bootstrap_95_upper": "", "mcnemar_p": ""},
        {"scope": "Stage 2", "arm": "R", "denominator": v["phase8_cohort"]["eligible_count"], "valid_output": "", "compile_success": "", "repair_time_success": "", "invalid_or_length": "", "validated": stage2["paired"]["retry_validated"], "validated_rate": stage2["paired"]["retry_validated"] / v["phase8_cohort"]["eligible_count"], "both_success": "", "control_fail_treatment_success": "", "control_success_treatment_fail": "", "both_fail": "", "difference": "", "bootstrap_95_lower": "", "bootstrap_95_upper": "", "mcnemar_p": ""},
        {"scope": "Stage 2", "arm": "F", "denominator": v["phase8_cohort"]["eligible_count"], "valid_output": "", "compile_success": "", "repair_time_success": "", "invalid_or_length": "", "validated": stage2["paired"]["feedback_validated"], "validated_rate": stage2["paired"]["feedback_validated"] / v["phase8_cohort"]["eligible_count"], "both_success": stage2["paired"]["both_success"], "control_fail_treatment_success": stage2["paired"]["retry_fail_feedback_success"], "control_success_treatment_fail": stage2["paired"]["retry_success_feedback_fail"], "both_fail": stage2["paired"]["both_fail"], "difference": stage2["paired"]["feedback_minus_retry"], "bootstrap_95_lower": stage2["paired"]["bootstrap_95_ci"]["lower"], "bootstrap_95_upper": stage2["paired"]["bootstrap_95_ci"]["upper"], "mcnemar_p": stage2["paired"]["mcnemar_exact"]["p_value_two_sided"]},
        {"scope": "End-to-end", "arm": "S0", "denominator": end_to_end["denominator"], "valid_output": "", "compile_success": "", "repair_time_success": "", "invalid_or_length": "", "validated": end_to_end["S0_initial_only"]["validated"], "validated_rate": end_to_end["S0_initial_only"]["rate"], "both_success": "", "control_fail_treatment_success": "", "control_success_treatment_fail": "", "both_fail": "", "difference": "", "bootstrap_95_lower": "", "bootstrap_95_upper": "", "mcnemar_p": ""},
        {"scope": "End-to-end", "arm": "SR", "denominator": end_to_end["denominator"], "valid_output": "", "compile_success": "", "repair_time_success": "", "invalid_or_length": "", "validated": end_to_end["SR_initial_plus_retry"]["validated"], "validated_rate": end_to_end["SR_initial_plus_retry"]["rate"], "both_success": "", "control_fail_treatment_success": "", "control_success_treatment_fail": "", "both_fail": "", "difference": "", "bootstrap_95_lower": "", "bootstrap_95_upper": "", "mcnemar_p": ""},
        {"scope": "End-to-end", "arm": "SF", "denominator": end_to_end["denominator"], "valid_output": "", "compile_success": "", "repair_time_success": "", "invalid_or_length": "", "validated": end_to_end["SF_initial_plus_feedback"]["validated"], "validated_rate": end_to_end["SF_initial_plus_feedback"]["rate"], "both_success": "", "control_fail_treatment_success": "", "control_success_treatment_fail": "", "both_fail": "", "difference": "", "bootstrap_95_lower": "", "bootstrap_95_upper": "", "mcnemar_p": ""},
    ]
    phase9 = v["phase9"]
    asan_rejected = _report_number(PHASE9_REPORT, r"Affected patches: ASan=(\d+)")
    ubsan_rejected = _report_number(PHASE9_REPORT, r"Affected patches: ASan=\d+, UBSan=(\d+)")
    patch_results = phase9["patch_results"]
    v3_applicable = sum(item["V3"] != "N/A" for item in patch_results)
    v3_pass = sum(item["V3"] == "PASS" for item in patch_results)
    v4_applicable = sum(item["V4"] != "N/A" for item in patch_results)
    v4_pass = sum(item["V4"] == "PASS" for item in patch_results)
    validation_rows = [
        {"section": "corpus", "label": "Formal patches", "numerator": phase9["patch_count"], "denominator": "", "rate": "", "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": f"{phase9['unique_case_count']} unique cases"},
        {"section": "ladder", "label": "V1 Plausible", "numerator": phase9["metrics"]["V1_plausible"], "denominator": phase9["patch_count"], "rate": phase9["metrics"]["V1_plausible"] / phase9["patch_count"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "repair-time validation"},
        {"section": "ladder", "label": "V2 Existing Validated", "numerator": phase9["metrics"]["V2_existing_validated"], "denominator": phase9["patch_count"], "rate": phase9["metrics"]["V2_existing_validated"] / phase9["patch_count"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "hidden validation"},
        {"section": "ladder", "label": "V3 Sanitizer-Clean", "numerator": v3_pass, "denominator": v3_applicable, "rate": v3_pass / v3_applicable, "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "1 V2 patch had V3 N/A"},
        {"section": "ladder", "label": "V4 Differential Survivor", "numerator": v4_pass, "denominator": v4_applicable, "rate": v4_pass / v4_applicable, "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "52 rejected; 17 V2 patches V4 N/A"},
        {"section": "ladder", "label": "Strongly Validated", "numerator": phase9["metrics"]["strongly_validated"], "denominator": phase9["patch_count"], "rate": phase9["metrics"]["strongly_validated"] / phase9["patch_count"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "V2 PASS and V3 PASS and V4 PASS"},
        {"section": "sanitizer audit", "label": "ASan patch rejection", "numerator": asan_rejected, "denominator": phase9["metrics"]["V2_existing_validated"], "rate": asan_rejected / phase9["metrics"]["V2_existing_validated"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "frozen Phase 9 report"},
        {"section": "sanitizer audit", "label": "UBSan patch rejection", "numerator": ubsan_rejected, "denominator": phase9["metrics"]["V2_existing_validated"], "rate": ubsan_rejected / phase9["metrics"]["V2_existing_validated"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "frozen Phase 9 report"},
        {"section": "differential audit", "label": "Candidates", "numerator": phase9["differential"]["candidate_count"], "denominator": "", "rate": "", "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "generated stress inputs"},
        {"section": "differential audit", "label": "Reference-accepted stress inputs", "numerator": phase9["differential"]["accepted_test_count"], "denominator": phase9["differential"]["candidate_count"], "rate": phase9["differential"]["accepted_test_count"] / phase9["differential"]["candidate_count"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": f"{phase9['differential']['zero_accepted_case_count']} cases had zero accepted tests"},
        {"section": "differential audit", "label": "Output-mismatch patches", "numerator": phase9["failure_modes"]["affected_patch_counts"]["differential_output_mismatch"], "denominator": v4_applicable, "rate": phase9["failure_modes"]["affected_patch_counts"]["differential_output_mismatch"] / v4_applicable, "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": f"{phase9['failure_modes']['finding_instance_counts']['differential_output_mismatch']} findings"},
        {"section": "differential audit", "label": "Timeout patches", "numerator": phase9["failure_modes"]["affected_patch_counts"]["differential_timeout"], "denominator": v4_applicable, "rate": phase9["failure_modes"]["affected_patch_counts"]["differential_timeout"] / v4_applicable, "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": ""},
        {"section": "differential audit", "label": "Runtime-error patches", "numerator": phase9["failure_modes"]["affected_patch_counts"].get("differential_runtime_error", 0), "denominator": v4_applicable, "rate": 0.0, "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": ""},
        {"section": "differential audit", "label": "Additional rejection", "numerator": phase9["metrics"]["additional_rejections"], "denominator": phase9["metrics"]["additional_rejection_denominator"], "rate": phase9["metrics"]["additional_rejection_rate"], "existing_v2": "", "strong": "", "absolute_drop": "", "relative_survival": "", "note": "V2 patches with V3/V4 applicable"},
    ]
    for phase, label in (("phase7", "Phase 7"), ("phase8_stage1", "Phase 8"), ("phase8_stage2", "Phase 8")):
        for arm, item in phase9["group_audits"][phase].items():
            existing_rate = item["validated"] / item["attempted"]
            strong_rate = item["strongly_validated"] / item["attempted"]
            validation_rows.append(
                {"section": "arm audit", "label": f"{label} {arm}", "numerator": "", "denominator": item["attempted"], "rate": "", "existing_v2": item["validated"], "strong": item["strongly_validated"], "absolute_drop": existing_rate - strong_rate, "relative_survival": item["strongly_validated"] / item["validated"], "note": "small cohort M=6" if phase == "phase8_stage2" else ""}
            )
    dataset_rows = [dict(item) for item in datasets["datasets"]]
    return {
        "table_fl_main": fl_rows,
        "table_repair_main": repair_rows,
        "table_feedback_main": feedback_rows,
        "table_validation_main": validation_rows,
        "table_dataset_summary": dataset_rows,
        "dataset_overlap_matrix": datasets["matrix"],
        "table_cost_summary": build_cost_rows(v),
    }


def build_experiment_registry(v: dict[str, Any], datasets: dict[str, Any]) -> dict[str, Any]:
    dataset_by_name = {item["dataset"]: item for item in datasets["datasets"]}
    entries = [
        {
            "phase": 4,
            "experiment_name": "Original Line-Level Ochiai Pilot",
            "dataset": "FL Pilot",
            "case_count": 50,
            "random_seed": 20260815,
            "protocol_version": "line-sbfl-pilot-v1",
            "artifact_path": _relative(FAULT_LOCALIZATION_EVALUATION),
            "report_path": _relative(FAULT_LOCALIZATION_REPORT),
            "manifest_hash": dataset_by_name["FL Pilot"]["manifest_sha256"],
            "artifact_set_hash": _sha256(FAULT_LOCALIZATION_EVALUATION),
            "commit_sha": INTRODUCTION_COMMITS["phase4"],
            "main_metrics": _metric_row("Phase 4", "Original line Ochiai", v["fl5"]["metrics"]["ochiai"]),
            "status": "formal_frozen",
        },
        {
            "phase": 5,
            "experiment_name": "Branch-Aware FL-v1 Pilot",
            "dataset": "FL Pilot",
            "case_count": 50,
            "random_seed": 20260815,
            "protocol_version": "fl-v1",
            "artifact_path": _relative(FAULT_LOCALIZATION_BRANCH_EVALUATION),
            "report_path": "benchmark/reports/fault_localization_branch_report.md",
            "manifest_hash": dataset_by_name["FL Pilot"]["manifest_sha256"],
            "artifact_set_hash": _sha256(FAULT_LOCALIZATION_BRANCH_EVALUATION),
            "commit_sha": INTRODUCTION_COMMITS["phase5"],
            "main_metrics": _metric_row("Phase 5", "Branch-aware FL-v1", v["fl5"]["metrics"]["ochiai_branch_tiebreak"]),
            "status": "formal_frozen",
        },
        {
            "phase": 6,
            "experiment_name": "Independent Fault Localization Evaluation",
            "dataset": "Independent FL Evaluation",
            "case_count": 300,
            "random_seed": 20260816,
            "protocol_version": v["fl6"]["method_version"],
            "artifact_path": _relative(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION),
            "report_path": _relative(FAULT_LOCALIZATION_INDEPENDENT_REPORT),
            "manifest_hash": dataset_by_name["Independent FL Evaluation"]["manifest_sha256"],
            "artifact_set_hash": _sha256(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION),
            "commit_sha": INTRODUCTION_COMMITS["phase6"],
            "main_metrics": {
                "original_mrr": v["fl6"]["metrics"]["ochiai"]["mrr"],
                "fl_v1_mrr": v["fl6"]["metrics"]["ochiai_branch_tiebreak"]["mrr"],
                "mrr_difference": v["fl6"]["bootstrap"]["deterministic_mrr_difference"]["observed_difference"],
                "average_rank_mrr_difference": v["fl6"]["bootstrap"]["average_rank_mrr_difference"]["observed_difference"],
            },
            "status": "formal_frozen",
        },
        {
            "phase": 7,
            "experiment_name": "LLM Repair Evidence Ablation",
            "dataset": "Phase 7 Repair Pilot",
            "case_count": 50,
            "random_seed": 20260817,
            "protocol_version": v["phase7_run"]["protocol_version"],
            "artifact_path": _relative(REPAIR_EVALUATION),
            "report_path": _relative(REPAIR_REPORT),
            "manifest_hash": dataset_by_name["Phase 7 Repair Pilot"]["manifest_sha256"],
            "artifact_set_hash": v["phase7"]["experiment"]["artifact_integrity"]["artifact_set_hash"],
            "commit_sha": INTRODUCTION_COMMITS["phase7"],
            "main_metrics": {arm: v["phase7"]["groups"][arm]["validated_rate"] for arm in ("A", "B", "C")},
            "status": "formal_frozen",
        },
        {
            "phase": 8,
            "experiment_name": "Execution Feedback Stage 1 Initial",
            "dataset": "Phase 8 Repair Evaluation",
            "case_count": 100,
            "random_seed": 20260820,
            "protocol_version": v["phase8_stage1"]["protocol_version"],
            "artifact_path": _relative(PHASE8_STAGE1_MANIFEST),
            "report_path": _relative(PHASE8_STAGE1_REPORT),
            "manifest_hash": dataset_by_name["Phase 8 Repair Evaluation"]["manifest_sha256"],
            "artifact_set_hash": v["phase8_stage1"]["overall_manifest_hash"],
            "commit_sha": INTRODUCTION_COMMITS["phase8_stage1"],
            "main_metrics": {"attempted": 100, "received": 100, "repair_time_success": 85, "validated": 85, "eligible": 6},
            "status": "formal_frozen",
        },
        {
            "phase": 8,
            "experiment_name": "Retry vs Execution Feedback Stage 2",
            "dataset": "Phase 8 Repair Evaluation eligible cohort",
            "case_count": 6,
            "random_seed": 20260820,
            "protocol_version": v["phase8_stage2"]["protocol_version"],
            "artifact_path": _relative(PHASE8_STAGE2_RESULT_MANIFEST),
            "report_path": _relative(PHASE8_FINAL_REPORT),
            "manifest_hash": v["phase8_stage2"]["overall_manifest_hash"],
            "artifact_set_hash": v["phase8_stage2"]["artifact_set_hash"],
            "commit_sha": INTRODUCTION_COMMITS["phase8_stage2"],
            "main_metrics": {"R_validated": 4, "F_validated": 4, "denominator": 6, "difference": 0.0},
            "status": "formal_frozen_small_cohort",
        },
        {
            "phase": 9,
            "experiment_name": "Patch Validation Strength and Overfitting",
            "dataset": "Formal Phase 7/8 Patch Corpus",
            "case_count": v["phase9"]["unique_case_count"],
            "random_seed": 20260820,
            "protocol_version": v["phase9"]["protocol_version"],
            "artifact_path": _relative(PHASE9_RESULT_MANIFEST),
            "report_path": _relative(PHASE9_REPORT),
            "manifest_hash": v["phase9"]["overall_manifest_hash"],
            "artifact_set_hash": v["phase9"]["corpus_manifest_hash"],
            "commit_sha": INTRODUCTION_COMMITS["phase9"],
            "main_metrics": {
                "patch_count": v["phase9"]["patch_count"],
                "V1": v["phase9"]["metrics"]["V1_plausible"],
                "V2": v["phase9"]["metrics"]["V2_existing_validated"],
                "V4_rejections": v["phase9"]["metrics"]["V2_to_V4_rejections"],
                "strongly_validated": v["phase9"]["metrics"]["strongly_validated"],
            },
            "status": "formal_frozen",
        },
    ]
    value: dict[str, Any] = {
        "entries": entries,
        "experiment_count": len(entries),
        "protocol_version": "final-experiment-registry-v1",
        "source_commit_sha": SOURCE_COMMIT,
        "status": "frozen",
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def build_reproducibility_registry(v: dict[str, Any]) -> dict[str, Any]:
    entries = [
        ("Phase 4 line-level evaluation", "file SHA-256", _sha256(FAULT_LOCALIZATION_EVALUATION), 4, _relative(FAULT_LOCALIZATION_EVALUATION)),
        ("Phase 5 branch evaluation", "file SHA-256", _sha256(FAULT_LOCALIZATION_BRANCH_EVALUATION), 5, _relative(FAULT_LOCALIZATION_BRANCH_EVALUATION)),
        ("Phase 6 independent evaluation", "file SHA-256", _sha256(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION), 6, _relative(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION)),
        ("Phase 7 formal artifact set", "canonical SHA-256 artifact set", v["phase7"]["experiment"]["artifact_integrity"]["artifact_set_hash"], 7, _relative(REPAIR_EVALUATION)),
        ("Phase 8 Stage 1 artifact set", "canonical SHA-256 manifest", v["phase8_stage1"]["overall_manifest_hash"], 8, _relative(PHASE8_STAGE1_MANIFEST)),
        ("Phase 8 eligible cohort", "canonical SHA-256 manifest", v["phase8_cohort"]["overall_manifest_hash"], 8, _relative(PHASE8_ELIGIBLE_COHORT)),
        ("Phase 8 Stage 2 artifact set", "canonical SHA-256 artifact set", v["phase8_stage2"]["artifact_set_hash"], 8, _relative(PHASE8_STAGE2_RESULT_MANIFEST)),
        ("Phase 8 Stage 2 result", "canonical SHA-256 manifest", v["phase8_stage2"]["overall_manifest_hash"], 8, _relative(PHASE8_STAGE2_RESULT_MANIFEST)),
        ("Phase 9 formal patch corpus", "canonical SHA-256 manifest", v["phase9_corpus"]["overall_manifest_hash"], 9, _relative(PHASE9_PATCH_CORPUS)),
        ("Phase 9 differential stress set", "canonical SHA-256 manifest", v["phase9_differential"]["overall_manifest_hash"], 9, _relative(PHASE9_DIFFERENTIAL_MANIFEST)),
        ("Phase 9 validation result", "canonical SHA-256 manifest", v["phase9"]["overall_manifest_hash"], 9, _relative(PHASE9_RESULT_MANIFEST)),
    ]
    values = [
        {"artifact_name": name, "hash_algorithm": algorithm, "sha256": digest, "source_phase": phase, "source_path": path, "verification_result": "passed"}
        for name, algorithm, digest, phase, path in entries
    ]
    value: dict[str, Any] = {
        "artifacts": values,
        "protocol_version": "final-reproducibility-registry-v1",
        "status": "passed",
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def _git(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        input=input_text,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def build_integrity_audit(v: dict[str, Any]) -> dict[str, Any]:
    source_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
    ).returncode == 0
    _assert_equal("source commit is an ancestor of HEAD", source_is_ancestor, True)
    actual = {
        "phase4_evaluation_file": _sha256(FAULT_LOCALIZATION_EVALUATION),
        "phase5_evaluation_file": _sha256(FAULT_LOCALIZATION_BRANCH_EVALUATION),
        "phase6_evaluation_file": _sha256(FAULT_LOCALIZATION_INDEPENDENT_EVALUATION),
        "phase7_artifact_set": v["phase7"]["experiment"]["artifact_integrity"]["artifact_set_hash"],
        "phase8_stage1": v["phase8_stage1"]["overall_manifest_hash"],
        "phase8_cohort": v["phase8_cohort"]["overall_manifest_hash"],
        "phase8_stage2_artifacts": v["phase8_stage2"]["artifact_set_hash"],
        "phase8_stage2_result": v["phase8_stage2"]["overall_manifest_hash"],
        "phase9_corpus": v["phase9_corpus"]["overall_manifest_hash"],
        "phase9_differential": v["phase9_differential"]["overall_manifest_hash"],
        "phase9_result": v["phase9"]["overall_manifest_hash"],
    }
    for name, expected in EXPECTED_HASHES.items():
        _assert_equal(f"frozen hash {name}", actual[name], expected)
    frozen_paths = (
        "benchmark/results/fault_localization",
        "benchmark/results/fault_localization_independent",
        "benchmark/results/repair/evidence_ablation.json",
        "benchmark/metadata/repair/formal_run_v1.json",
        "benchmark/metadata/repair_phase8",
        "benchmark/metadata/validation",
        "benchmark/reports/fault_localization_pilot_report.md",
        "benchmark/reports/fault_localization_branch_report.md",
        "benchmark/reports/fault_localization_independent_evaluation.md",
        "benchmark/reports/llm_repair_evidence_ablation.md",
        "benchmark/reports/execution_feedback_stage1.md",
        "benchmark/reports/execution_feedback_formal.md",
        "benchmark/reports/patch_validation_overfitting.md",
    )
    changed = _git("diff", "--name-only", SOURCE_COMMIT, "--", *frozen_paths).splitlines()
    _assert_equal("unexpected frozen artifact diff", changed, [])
    return {
        "checked_hashes": actual,
        "frozen_paths_changed": changed,
        "large_raw_artifacts_reread": False,
        "method": "self-hashed manifests, frozen expected hashes, tracked file SHA-256, and zero-diff audit",
        "source_commit_is_ancestor": source_is_ancestor,
        "source_commit_sha": SOURCE_COMMIT,
        "status": "passed",
    }


def _candidate_paths() -> list[Path]:
    names = _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    return [PROJECT_ROOT / name for name in names if (PROJECT_ROOT / name).is_file()]


def _walk_reasoning(value: Any) -> tuple[int, int]:
    metadata = 0
    raw = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"reasoning_content", "raw_reasoning"}:
                if isinstance(item, str):
                    raw += 1
                elif isinstance(item, dict) and set(item) <= {"characters", "present", "sha256"}:
                    metadata += 1
                elif item is not None:
                    raw += 1
            nested_metadata, nested_raw = _walk_reasoning(item)
            metadata += nested_metadata
            raw += nested_raw
    elif isinstance(value, list):
        for item in value:
            nested_metadata, nested_raw = _walk_reasoning(item)
            metadata += nested_metadata
            raw += nested_raw
    return metadata, raw


def build_leakage_audit(v: dict[str, Any]) -> dict[str, Any]:
    paths = _candidate_paths()
    env_files = [
        _relative(path)
        for path in paths
        if path.name == ".env" or path.name.endswith(".env") or path.name == "secrets.env"
    ]
    credential_pattern = re.compile(
        r"(?:DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*=\s*['\"]?([A-Za-z0-9._-]{16,})|"
        r"sk-[A-Za-z0-9]{20,}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
    )
    credential_hits = []
    reasoning_metadata = 0
    raw_reasoning = 0
    for path in paths:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if credential_pattern.search(text):
            credential_hits.append(_relative(path))
        if path.suffix in {".json", ".jsonl"} and ('"reasoning_content"' in text or '"raw_reasoning"' in text):
            try:
                values = [json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix == ".jsonl" else [json.loads(text)]
            except json.JSONDecodeError:
                raw_reasoning += 1
            else:
                for value in values:
                    metadata, raw = _walk_reasoning(value)
                    reasoning_metadata += metadata
                    raw_reasoning += raw
    binary_suffixes = {".o", ".so", ".a", ".exe", ".class", ".pyc"}
    binaries = [_relative(path) for path in paths if path.suffix.lower() in binary_suffixes]
    prompt_boundaries = {
        "phase6": v["fl6"]["leakage_scan"]["status"],
        "phase7": v["phase7"]["leakage_scan"]["status"],
        "phase8_stage2": v["phase8_stage2"]["leakage_audit"]["status"],
        "phase9": "passed" if (
            v["phase9"]["leakage_audit"]["llm_calls"] == 0
            and not v["phase9"]["leakage_audit"]["raw_reasoning_committed"]
            and not v["phase9"]["leakage_audit"]["generated_input_text_committed"]
        ) else "failed",
    }
    status = "passed" if not env_files and not credential_hits and not raw_reasoning and not binaries and set(prompt_boundaries.values()) == {"passed"} else "failed"
    return {
        "binary_files": binaries,
        "credential_pattern_hits": credential_hits,
        "env_or_secret_files": env_files,
        "prompt_boundary_audits": prompt_boundaries,
        "raw_reasoning_fields": raw_reasoning,
        "reasoning_metadata_only_fields": reasoning_metadata,
        "status": status,
    }


def _largest_git_objects(limit: int = 10) -> list[dict[str, Any]]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)"],
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    object_list = _git("rev-list", "--objects", "--all")
    stdout, stderr = process.communicate(object_list)
    if process.returncode:
        raise RuntimeError(f"git object size audit failed: {stderr}")
    objects = []
    for line in stdout.splitlines():
        parts = line.split(" ", 3)
        if len(parts) < 3 or parts[0] != "blob":
            continue
        objects.append(
            {
                "object": parts[1],
                "path": parts[3] if len(parts) == 4 else "",
                "size_bytes": int(parts[2]),
            }
        )
    return sorted(objects, key=lambda item: (-item["size_bytes"], item["path"]))[:limit]


def build_repository_size_audit() -> dict[str, Any]:
    files = [
        {"path": _relative(path), "size_bytes": path.stat().st_size}
        for path in _candidate_paths()
    ]
    files.sort(key=lambda item: (-item["size_bytes"], item["path"]))
    ignored_samples = [
        "benchmark/artifacts/repair/formal_evidence_ablation/__audit__.json",
        "benchmark/artifacts/repair_phase8/initial/__audit__.json",
        "benchmark/artifacts/repair_phase8/retry_control/__audit__.json",
        "benchmark/artifacts/repair_phase8/feedback/__audit__.json",
        "benchmark/artifacts/validation_phase9/__audit__.json",
        "benchmark/datasets/codeflaws/raw/__audit__.dat",
    ]
    ignored = []
    for sample in ignored_samples:
        result = subprocess.run(
            ["git", "check-ignore", "-q", sample], cwd=PROJECT_ROOT
        )
        ignored.append({"sample_path": sample, "ignored": result.returncode == 0})
    return {
        "history_rewritten": False,
        "ignored_raw_directory_samples": ignored,
        "largest_git_objects": _largest_git_objects(),
        "largest_tracked_or_planned_files": files[:20],
        "status": "warning" if any(item["size_bytes"] > 10 * 1024 * 1024 for item in files) else "passed",
        "tracked_or_planned_files_over_10_mb": [item for item in files if item["size_bytes"] > 10 * 1024 * 1024],
        "warning_threshold_bytes": 10 * 1024 * 1024,
    }


def _csv_text(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        raise ValueError("final table cannot be empty")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _display(key: str, value: Any) -> str:
    if value == "":
        return ""
    percent_fields = {
        "top_1", "top_3", "top_5", "top_10", "validated_rate", "rate",
        "paired_difference", "bootstrap_95_lower", "bootstrap_95_upper",
        "difference", "absolute_drop", "relative_survival",
    }
    if key in percent_fields and isinstance(value, (int, float)):
        return f"{100 * value:.2f}%"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _markdown_table(title: str, rows: Sequence[dict[str, Any]]) -> str:
    fields = list(rows[0])
    lines = [f"# {title}", "", "| " + " | ".join(fields) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_display(field, row[field]) for field in fields) + " |")
    lines.extend(["", "Generated deterministically from frozen formal artifacts and reports.", ""])
    return "\n".join(lines)


def write_tables(tables: dict[str, list[dict[str, Any]]]) -> list[Path]:
    FINAL_REPORT_TABLE_ROOT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rows in tables.items():
        csv_path = FINAL_REPORT_TABLE_ROOT / f"{name}.csv"
        md_path = FINAL_REPORT_TABLE_ROOT / f"{name}.md"
        csv_path.write_text(_csv_text(rows), encoding="utf-8")
        md_path.write_text(_markdown_table(name.replace("_", " ").title(), rows), encoding="utf-8")
        written.extend((csv_path, md_path))
    return written


def build_plot_rows(v: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fl = v["fl6"]
    plot_fl = []
    for method, label in (("ochiai", "Original Ochiai"), ("ochiai_branch_tiebreak", "FL-v1")):
        metrics = fl["metrics"][method]
        for metric, key in (("Top-1", "top_1_accuracy"), ("Top-3", "top_3_accuracy"), ("Top-5", "top_5_accuracy"), ("Top-10", "top_10_accuracy"), ("MRR", "mrr")):
            plot_fl.append({"panel": "ranking", "metric": metric, "series": label, "value": metrics[key]})
        ties = fl["tie_statistics"][method]
        for metric, key in (("Top-score tie cases", "cases_with_top_score_tie"), ("Fault-tie cases", "cases_with_fault_line_tied"), ("Mean maximum tie", "average_max_tie_size"), ("Mean fault tie", "average_fault_tie_size")):
            plot_fl.append({"panel": "ties", "metric": metric, "series": label, "value": ties[key]})
    audits = v["phase9"]["group_audits"]["phase7"]
    plot_repair = []
    for arm in ("A", "B", "C"):
        item = audits[arm]
        plot_repair.extend(
            [
                {"arm": arm, "validation": "Existing V2", "rate": item["validated"] / item["attempted"]},
                {"arm": arm, "validation": "Strong", "rate": item["strongly_validated"] / item["attempted"]},
            ]
        )
    stage2 = v["phase8_stage2"]
    plot_feedback = [
        {"panel": "end_to_end", "outcome": key.split("_")[0], "value": item["rate"]}
        for key, item in stage2["end_to_end"].items()
        if key != "denominator"
    ]
    plot_feedback.extend(
        {"panel": "paired", "outcome": label, "value": stage2["paired"][key]}
        for label, key in (
            ("both success", "both_success"),
            ("R fail to F success", "retry_fail_feedback_success"),
            ("R success to F fail", "retry_success_feedback_fail"),
            ("both fail", "both_fail"),
        )
    )
    p9 = v["phase9"]
    plot_validation = [
        {"stage": "V1 Plausible", "count": p9["metrics"]["V1_plausible"], "denominator": p9["patch_count"]},
        {"stage": "V2 Existing Validated", "count": p9["metrics"]["V2_existing_validated"], "denominator": p9["patch_count"]},
        {"stage": "V3 Sanitizer-Clean", "count": sum(item["V3"] == "PASS" for item in p9["patch_results"]), "denominator": sum(item["V3"] != "N/A" for item in p9["patch_results"])},
        {"stage": "V4 Differential Survivor", "count": sum(item["V4"] == "PASS" for item in p9["patch_results"]), "denominator": sum(item["V4"] != "N/A" for item in p9["patch_results"])},
        {"stage": "Strongly Validated", "count": p9["metrics"]["strongly_validated"], "denominator": p9["patch_count"]},
    ]
    return {
        "plot_fl": plot_fl,
        "plot_repair": plot_repair,
        "plot_feedback": plot_feedback,
        "plot_validation_ladder": plot_validation,
    }


def write_plot_data(plot_rows: dict[str, list[dict[str, Any]]]) -> list[Path]:
    paths = []
    for name, rows in plot_rows.items():
        path = FINAL_REPORT_TABLE_ROOT / f"{name}.csv"
        path.write_text(_csv_text(rows), encoding="utf-8")
        paths.append(path)
    json_path = FINAL_REPORT_TABLE_ROOT / "plot_data.json"
    json_path.write_text(json.dumps(plot_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths.append(json_path)
    return paths


def _hash_collection(paths: Iterable[Path]) -> str:
    values = [
        {"path": _relative(path), "sha256": _sha256(path)}
        for path in sorted(paths)
    ]
    return canonical_hash(values)


def render_research_summary(
    v: dict[str, Any],
    datasets: dict[str, Any],
    registry: dict[str, Any],
    reproducibility: dict[str, Any],
    cost_rows: list[dict[str, Any]],
) -> str:
    fl6 = v["fl6"]
    p7 = v["phase7"]
    p8 = v["phase8_stage2"]
    p9 = v["phase9"]
    total_cost = cost_rows[-1]
    return f"""# CodeDoctor Final Research Summary

## 1. Research Scope

CodeDoctor's frozen research pipeline is: buggy C/C++ program -> repair tests and coverage -> fault localization -> LLM repair -> execution feedback -> patch validation -> benchmark evaluation. The four research parts are fault localization (Phases 4-6), repair evidence (Phase 7), execution feedback (Phase 8), and validation strength (Phase 9). No fifth core direction is introduced.

## 2. Experimental Datasets

The formal datasets contain 50 FL Pilot, 300 independent FL evaluation, 50 Phase 7 repair, and 100 Phase 8 repair cases. Their six pairwise overlaps are all zero. Dataset manifest identities and the full overlap matrix are frozen in `{_relative(FINAL_DATASET_OVERLAP)}`.

## 3. RQ1 - Fault Localization

On the independent 300-case evaluation, deterministic MRR increased from {fl6['metrics']['ochiai']['mrr']:.4f} to {fl6['metrics']['ochiai_branch_tiebreak']['mrr']:.4f}; average-rank MRR increased from {fl6['metrics']['ochiai']['tie_aware']['average_rank']['mrr']:.4f} to {fl6['metrics']['ochiai_branch_tiebreak']['tie_aware']['average_rank']['mrr']:.4f}. Top-score ties fell from 231 to 157 and fault ties from 256 to 205. Coverage equivalence is associated with many line-level ties, and branch evidence can break some of them. Not every case improves: average-rank outcomes were 99 improved, 79 unchanged, and 122 regressed. Boundaries include non-executable faults, straight-line ambiguity, weak 0-PASS spectra, and misleading branch evidence.

## 4. RQ2 - Repair-Time Evidence

Phase 7 validated A={p7['groups']['A']['validated']}/50, B={p7['groups']['B']['validated']}/50, and C={p7['groups']['C']['validated']}/50. FL-v1 alone did not improve B over A (-2 percentage points). Adding frozen runtime evidence on top of FL-v1 was associated with a +14-point paired difference for C versus B, with 8 improvements and 1 regression. This is one stochastic 50-case, single-model run with finite validation and unadjusted multiple comparisons, not a general causal proof.

## 5. RQ3 - Execution Feedback

A second repair opportunity rescued some first-round failures. In the frozen M=6 paired cohort, R and F both validated 4/6: both success=3, R fail/F success=1, R success/F fail=1, both fail=1. The difference is zero, bootstrap CI [{p8['paired']['bootstrap_95_ci']['lower']:+.1f}, {p8['paired']['bootstrap_95_ci']['upper']:+.1f}], and exact McNemar p={p8['paired']['mcnemar_exact']['p_value_two_sided']:.1f}. This is paired case-level evidence and does not establish an aggregate feedback advantage.

## 6. RQ4 - Patch Validation Strength

The formal corpus contains {p9['patch_count']} patches from {p9['unique_case_count']} cases. V1 plausible={p9['metrics']['V1_plausible']}, V2 existing validated={p9['metrics']['V2_existing_validated']}, and strongly validated={p9['metrics']['strongly_validated']}. V3 produced no patch rejection. Among 201 V4-applicable V2 patches, 52 (25.9%) were rejected by reference-based differential stress testing. Strongly Validated Patch is not Formally Correct Patch.

## 7. Cross-Phase Findings

1. Coverage equivalence contributes to SBFL ties, and branch evidence reduces some ties.
2. Better localization metrics do not automatically yield better LLM repair utility: FL-v1 improved Phase 6 localization, while Phase 7 B did not outperform A.
3. Runtime evidence showed stronger repair utility than static FL evidence in this frozen run: B=78% and C=92%, with cautious associative wording.
4. Validation strength changes apparent success substantially: Phase 7 C falls from 92% V2 to 70% strong, and Phase 8 Initial from 85% V2 to 55% strong.

## 8. Reproducibility

The final formal experiment registry hash is `{registry['overall_manifest_hash']}` and the reproducibility registry hash is `{reproducibility['overall_manifest_hash']}`. All registered frozen hashes and zero-diff checks passed. Raw large experiments were not rerun.

## 9. Cost

Formal LLM experiments attempted {total_cost['attempted_calls']} calls, received {total_cost['successful_responses']} responses, used {total_cost['total_tokens']:,} provider-reported tokens, and have an estimated usage cost of `${total_cost['estimated_cost_usd']:.8f}`. This is not a billing export. Final consolidation made zero LLM calls and cost `$0`.

## 10. Threats to Validity

- Internal: LLM stochasticity, single-attempt protocols, provider failures, length truncation, and finite tests.
- Construct: FL metrics are not repair utility; Validated and Strongly Validated do not mean Correct; reference-accepted stress inputs are not formally valid inputs.
- External: Codeflaws, competitive-programming C/C++ defects, and one LLM family/model limit generalization.
- Statistical: Phase 7 n=50, Phase 8 R/F n=6, dependent same-case patches, post-hoc subgroups, and multiple comparisons.

## 11. Final Conclusions

The frozen evidence supports four bounded contributions: empirical analysis of coverage-equivalence ties and branch tie-breaking; a strict-information-boundary repair evidence ablation; a paired design separating second-chance and feedback effects; and a validation ladder showing that hidden-test validation can overstate patch reliability. It does not support state-of-the-art, universal-superiority, or formal-correctness claims.
"""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_final_consolidation() -> dict[str, Any]:
    values = load_frozen_sources()
    validate_frozen_metrics(values)
    datasets = build_dataset_audit()
    tables = build_table_rows(values, datasets)
    registry = build_experiment_registry(values, datasets)
    reproducibility = build_reproducibility_registry(values)

    FINAL_METADATA_ROOT.mkdir(parents=True, exist_ok=True)
    _write_json(FINAL_DATASET_OVERLAP, datasets)
    _write_json(FINAL_EXPERIMENT_REGISTRY, registry)
    _write_json(FINAL_REPRODUCIBILITY_REGISTRY, reproducibility)
    table_paths = write_tables(tables)
    plot_paths = write_plot_data(build_plot_rows(values))
    summary = render_research_summary(values, datasets, registry, reproducibility, tables["table_cost_summary"])
    FINAL_RESEARCH_SUMMARY.write_text(summary, encoding="utf-8")

    integrity = build_integrity_audit(values)
    leakage = build_leakage_audit(values)
    repository_size = build_repository_size_audit()
    audit: dict[str, Any] = {
        "artifact_integrity": integrity,
        "discrepancies": [],
        "leakage": leakage,
        "metrics_cross_check": "passed",
        "real_llm_calls": 0,
        "repository_size": repository_size,
        "status": "passed" if integrity["status"] == leakage["status"] == "passed" else "failed",
    }
    audit["overall_manifest_hash"] = canonical_hash(audit)
    _write_json(FINAL_AUDIT_SUMMARY, audit)

    final_tables_hash = _hash_collection([*table_paths, *plot_paths])
    freeze: dict[str, Any] = {
        "artifact_integrity_status": integrity["status"],
        "final_commit_sha": None,
        "final_commit_sha_note": "Intentionally omitted to avoid a self-referential commit; bind the committed freeze file to the final Git commit externally.",
        "final_research_summary_sha256": _sha256(FINAL_RESEARCH_SUMMARY),
        "final_tables_hash": final_tables_hash,
        "formal_experiment_registry_hash": registry["overall_manifest_hash"],
        "freeze_date": "2026-08-20",
        "leakage_audit_status": leakage["status"],
        "pre_freeze_commit_sha": SOURCE_COMMIT,
        "protocol_version": "codedoctor-final-freeze-v1",
        "real_llm_calls": 0,
        "reproducibility_registry_hash": reproducibility["overall_manifest_hash"],
        "status": "frozen" if audit["status"] == "passed" else "blocked",
    }
    freeze["overall_manifest_hash"] = canonical_hash(freeze)
    _write_json(FINAL_FREEZE, freeze)
    return {
        "audit": audit,
        "datasets": datasets,
        "freeze": freeze,
        "registry": registry,
        "reproducibility": reproducibility,
        "tables": tables,
    }
