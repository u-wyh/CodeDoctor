"""Evaluate frozen FL-v1 on independent saved Codeflaws artifacts."""

import json
import statistics
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from benchmark.config import (
    CODEFLAWS_FL_EVALUATION,
    CODEFLAWS_FL_EVALUATION_EXCLUDED,
    CODEFLAWS_FL_EVALUATION_SUMMARY,
    FAULT_LOCALIZATION_INDEPENDENT_COVERAGE_ROOT,
    FAULT_LOCALIZATION_INDEPENDENT_EVALUATION,
    FAULT_LOCALIZATION_INDEPENDENT_GROUND_TRUTH,
    FAULT_LOCALIZATION_INDEPENDENT_RANKING_ROOT,
)
from benchmark.models import load_manifest

from .evaluation import TOP_K_VALUES, aggregate_metrics, evaluate_case
from .method_freeze import validate_frozen_method
from .models import CoverageMatrix, RankedLine
from .statistics import (
    exact_mcnemar,
    paired_bootstrap_difference,
    paired_change_counts,
)
from .tie_analysis import coverage_equivalence_classes, tie_group_sizes


METHODS = ("ochiai", "ochiai_branch_tiebreak")
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20260816
FORBIDDEN_LOCALIZATION_KEYS = {
    "fault_lines",
    "ground_truth",
    "heldout",
    "reference",
    "validation",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def artifact_leakage_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in FORBIDDEN_LOCALIZATION_KEYS):
                found.add(str(key))
            found.update(artifact_leakage_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(artifact_leakage_keys(nested))
    return found


def _reciprocal(rank: int | float | None) -> float:
    return 1.0 / rank if rank is not None else 0.0


def _method_case(metric: Any) -> dict[str, Any]:
    return {
        "average_fault_rank": metric.average_fault_rank,
        "average_reciprocal_rank": _reciprocal(metric.average_fault_rank),
        "best_fault_rank": metric.best_fault_rank,
        "deterministic_reciprocal_rank": metric.reciprocal_rank,
        "fault_tie_size": metric.fault_tie_size,
        "first_fault_rank": metric.first_fault_rank,
        "pessimistic_reciprocal_rank": _reciprocal(metric.worst_fault_rank),
        "top_k": {str(key): value for key, value in metric.top_k.items()},
        "worst_fault_rank": metric.worst_fault_rank,
    }


def repair_test_group(total: int) -> str:
    if total <= 2:
        return "1-2"
    if total <= 5:
        return "3-5"
    return "6+"


def pass_test_group(passed: int) -> str:
    return "0 PASS" if passed == 0 else ">=1 PASS"


def coverage_diversity_group(ratio: float) -> str:
    if ratio <= 0.25:
        return "low (<=0.25)"
    if ratio <= 0.5:
        return "medium (0.25-0.5)"
    return "high (>0.5)"


def fault_class_group(size: int | None) -> str:
    if size is None:
        return "non-executable"
    if size == 1:
        return "1"
    if size <= 5:
        return "2-5"
    if size <= 10:
        return "6-10"
    return ">10"


def is_non_executable_fault(
    fault_lines: tuple[int, ...], executable_lines: set[int]
) -> bool:
    return not any(line in executable_lines for line in fault_lines)


def has_straight_line_ambiguity(
    fault_lines: tuple[int, ...],
    ranking: tuple[RankedLine, ...],
    vectors: dict[int, tuple[int, ...]],
) -> bool:
    fault_set = set(fault_lines)
    ranked_by_line = {item.line: item for item in ranking}
    for fault_line in fault_lines:
        fault_entry = ranked_by_line.get(fault_line)
        if fault_entry is None:
            continue
        for candidate in ranking:
            if (
                candidate.line not in fault_set
                and candidate.tie_start_rank == fault_entry.tie_start_rank
                and candidate.tie_end_rank == fault_entry.tie_end_rank
                and vectors[candidate.line] == vectors[fault_line]
            ):
                return True
    return False


def _subgroup_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = [
        case["methods"]["ochiai"]["average_reciprocal_rank"] for case in cases
    ]
    treatment = [
        case["methods"]["ochiai_branch_tiebreak"]["average_reciprocal_rank"]
        for case in cases
    ]
    return {
        "average_rank_mrr": {
            "branch_aware": statistics.fmean(treatment) if treatment else 0.0,
            "difference": (
                statistics.fmean(treatment) - statistics.fmean(baseline)
                if treatment
                else 0.0
            ),
            "original": statistics.fmean(baseline) if baseline else 0.0,
        },
        "cases": len(cases),
        "paired_changes": paired_change_counts(baseline, treatment),
    }


def _group_cases(
    cases: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        groups.setdefault(key(case), []).append(case)
    return {
        name: _subgroup_summary(values)
        for name, values in sorted(groups.items())
    }


def _tie_origin(
    ranking: tuple[RankedLine, ...], vectors: dict[int, tuple[int, ...]]
) -> dict[str, int | bool]:
    groups: dict[tuple[int, int], list[int]] = {}
    for item in ranking:
        groups.setdefault((item.tie_start_rank, item.tie_end_rank), []).append(
            item.line
        )
    tied = [lines for lines in groups.values() if len(lines) > 1]
    identical = [
        lines for lines in tied if len({vectors[line] for line in lines}) == 1
    ]
    top = (
        groups.get((ranking[0].tie_start_rank, ranking[0].tie_end_rank), [])
        if ranking
        else []
    )
    return {
        "tie_groups": len(tied),
        "tie_groups_with_identical_coverage": len(identical),
        "top_tie_is_single_coverage_class": (
            len(top) > 1 and len({vectors[line] for line in top}) == 1
        ),
    }


def _case_record(
    case: Any,
    matrix: CoverageMatrix,
    ranking_document: dict[str, Any],
    fault_lines: tuple[int, ...],
    algorithm_metrics: dict[str, list[Any]],
) -> dict[str, Any]:
    vectors = {
        line: tuple(int(line in test.covered_lines) for test in matrix.tests)
        for line in matrix.executable_lines
    }
    equivalence = coverage_equivalence_classes(matrix)
    class_by_line = {
        line: group for group in equivalence for line in group.lines
    }
    method_data = {}
    rankings: dict[str, tuple[RankedLine, ...]] = {}
    for method in METHODS:
        ranking = tuple(
            RankedLine(**item)
            for item in ranking_document["rankings"].get(method, [])
        )
        rankings[method] = ranking
        metric = evaluate_case(ranking, fault_lines)
        algorithm_metrics[method].append(metric)
        sizes = tie_group_sizes(ranking)
        method_data[method] = {
            **_method_case(metric),
            "max_tie_size": max(sizes, default=0),
            "top_score_tied": bool(
                ranking
                and ranking[0].tie_end_rank > ranking[0].tie_start_rank
            ),
        }

    non_executable = is_non_executable_fault(fault_lines, set(vectors))
    straight_line_ambiguity = has_straight_line_ambiguity(
        fault_lines, rankings["ochiai_branch_tiebreak"], vectors
    )

    fault_class_sizes = [
        len(class_by_line[line].lines)
        for line in fault_lines
        if line in class_by_line
    ]
    representative_fault_class_size = (
        max(fault_class_sizes) if fault_class_sizes else None
    )
    diversity_ratio = len(equivalence) / len(matrix.executable_lines)
    original_tie_origin = _tie_origin(rankings["ochiai"], vectors)
    original_average_rr = method_data["ochiai"]["average_reciprocal_rank"]
    branch_average_rr = method_data["ochiai_branch_tiebreak"][
        "average_reciprocal_rank"
    ]
    return {
        "average_rank_reciprocal_difference": branch_average_rr - original_average_rr,
        "branch_outcomes": len(matrix.executable_branches),
        "case_id": matrix.case_id,
        "coverage_diversity_ratio": diversity_ratio,
        "defect_class": str(case.metadata.get("defect_class") or "unknown"),
        "executable_lines": len(matrix.executable_lines),
        "failed_tests": matrix.failed_tests,
        "fault_equivalence_class_size": representative_fault_class_size,
        "fault_equivalence_class_sizes": fault_class_sizes,
        "fault_lines": list(fault_lines),
        "max_equivalence_class_size": max(
            (len(group.lines) for group in equivalence), default=0
        ),
        "methods": method_data,
        "non_executable_fault": non_executable,
        "original_tie_origin": original_tie_origin,
        "passed_tests": matrix.passed_tests,
        "repair_tests": len(matrix.tests),
        "straight_line_ambiguity": straight_line_ambiguity,
        "unique_coverage_vectors": len(equivalence),
    }


def _tie_statistics(cases: list[dict[str, Any]], method: str) -> dict[str, Any]:
    values = [case["methods"][method] for case in cases]
    fault_ties = [
        value["fault_tie_size"]
        for value in values
        if value["fault_tie_size"] is not None
    ]
    return {
        "average_fault_tie_size": (
            statistics.fmean(fault_ties) if fault_ties else 0.0
        ),
        "average_max_tie_size": statistics.fmean(
            value["max_tie_size"] for value in values
        ),
        "cases_with_fault_line_tied": sum(
            value["fault_tie_size"] is not None
            and value["fault_tie_size"] > 1
            for value in values
        ),
        "cases_with_top_score_tie": sum(
            value["top_score_tied"] for value in values
        ),
    }


def build_independent_evaluation() -> dict[str, Any]:
    validate_frozen_method()
    cases = list(load_manifest(CODEFLAWS_FL_EVALUATION))
    ground_truth = {
        item["case_id"]: tuple(item["fault_lines"])
        for item in _load_jsonl(FAULT_LOCALIZATION_INDEPENDENT_GROUND_TRUTH)
    }
    algorithm_metrics: dict[str, list[Any]] = {name: [] for name in METHODS}
    per_case = []
    leakage: dict[str, list[str]] = {}
    for case in cases:
        coverage_path = (
            FAULT_LOCALIZATION_INDEPENDENT_COVERAGE_ROOT / f"{case.case_id}.json"
        )
        ranking_path = (
            FAULT_LOCALIZATION_INDEPENDENT_RANKING_ROOT / f"{case.case_id}.json"
        )
        coverage_document = _load_json(coverage_path)
        ranking_document = _load_json(ranking_path)
        found = artifact_leakage_keys(coverage_document) | artifact_leakage_keys(
            ranking_document
        )
        if found:
            leakage[case.case_id] = sorted(found)
        if ranking_document.get("method_version") != "fl-v1":
            raise ValueError(f"non-frozen method artifact: {ranking_path}")
        if set(ranking_document.get("rankings", {})) != set(METHODS):
            raise ValueError(f"unexpected evaluated methods: {ranking_path}")
        per_case.append(
            _case_record(
                case,
                CoverageMatrix.from_dict(coverage_document),
                ranking_document,
                ground_truth[case.case_id],
                algorithm_metrics,
            )
        )
    if leakage:
        raise ValueError(f"localization artifact leakage detected: {leakage}")

    metrics = {
        name: aggregate_metrics(values) for name, values in algorithm_metrics.items()
    }
    baseline_rr = [
        case["methods"]["ochiai"]["deterministic_reciprocal_rank"]
        for case in per_case
    ]
    treatment_rr = [
        case["methods"]["ochiai_branch_tiebreak"][
            "deterministic_reciprocal_rank"
        ]
        for case in per_case
    ]
    baseline_average_rr = [
        case["methods"]["ochiai"]["average_reciprocal_rank"]
        for case in per_case
    ]
    treatment_average_rr = [
        case["methods"]["ochiai_branch_tiebreak"]["average_reciprocal_rank"]
        for case in per_case
    ]
    mcnemar = {}
    for top_k in TOP_K_VALUES:
        key = str(top_k)
        mcnemar[key] = exact_mcnemar(
            [case["methods"]["ochiai"]["top_k"][key] for case in per_case],
            [
                case["methods"]["ochiai_branch_tiebreak"]["top_k"][key]
                for case in per_case
            ],
        )

    tie_origins = [case["original_tie_origin"] for case in per_case]
    total_executable = sum(case["executable_lines"] for case in per_case)
    total_unique = sum(case["unique_coverage_vectors"] for case in per_case)
    exclusion_records = _load_jsonl(CODEFLAWS_FL_EVALUATION_EXCLUDED)
    selection_summary = _load_json(CODEFLAWS_FL_EVALUATION_SUMMARY)
    evaluation = {
        "bootstrap": {
            "average_rank_mrr_difference": paired_bootstrap_difference(
                baseline_average_rr,
                treatment_average_rr,
                samples=BOOTSTRAP_SAMPLES,
                seed=BOOTSTRAP_SEED,
            ),
            "deterministic_mrr_difference": paired_bootstrap_difference(
                baseline_rr,
                treatment_rr,
                samples=BOOTSTRAP_SAMPLES,
                seed=BOOTSTRAP_SEED,
            ),
        },
        "coverage_equivalence": {
            "average_diversity_ratio": statistics.fmean(
                case["coverage_diversity_ratio"] for case in per_case
            ),
            "average_fault_class_size": statistics.fmean(
                size
                for case in per_case
                for size in case["fault_equivalence_class_sizes"]
            ),
            "average_max_class_size": statistics.fmean(
                case["max_equivalence_class_size"] for case in per_case
            ),
            "coverage_equivalence_ratio": 1.0 - total_unique / total_executable,
            "executable_lines": total_executable,
            "unique_vectors": total_unique,
        },
        "dataset": {
            "defect_class_distribution": selection_summary[
                "defect_class_distribution"
            ],
            "dynamic_exclusion_reasons": selection_summary[
                "dynamic_exclusion_reasons"
            ],
            "dynamic_exclusions": selection_summary["dynamic_exclusions"],
            "evaluation_cases": len(per_case),
            "excluded_records": len(exclusion_records),
            "failed_repair_tests": sum(case["failed_tests"] for case in per_case),
            "passed_repair_tests": sum(case["passed_tests"] for case in per_case),
            "pilot_cases": selection_summary["pilot_size"],
            "pilot_overlap": selection_summary["pilot_overlap"],
            "repair_tests": sum(case["repair_tests"] for case in per_case),
            "seed": selection_summary["seed"],
            "static_exclusions": selection_summary["static_exclusions"],
        },
        "failure_boundaries": {
            "non_executable_fault_cases": sum(
                case["non_executable_fault"] for case in per_case
            ),
            "straight_line_ambiguity_cases": sum(
                case["straight_line_ambiguity"] for case in per_case
            ),
            "zero_pass_cases": sum(case["passed_tests"] == 0 for case in per_case),
        },
        "leakage_scan": {"cases_with_leakage": 0, "status": "passed"},
        "mcnemar": mcnemar,
        "method_version": "fl-v1",
        "metrics": metrics,
        "paired_changes": {
            "average_rank_reciprocal": paired_change_counts(
                baseline_average_rr, treatment_average_rr
            ),
            "deterministic_reciprocal": paired_change_counts(
                baseline_rr, treatment_rr
            ),
        },
        "per_case": per_case,
        "subgroups": {
            "coverage_diversity": _group_cases(
                per_case,
                lambda case: coverage_diversity_group(
                    case["coverage_diversity_ratio"]
                ),
            ),
            "fault_equivalence_class_size": _group_cases(
                per_case,
                lambda case: fault_class_group(
                    case["fault_equivalence_class_size"]
                ),
            ),
            "pass_tests": _group_cases(
                per_case, lambda case: pass_test_group(case["passed_tests"])
            ),
            "repair_tests": _group_cases(
                per_case, lambda case: repair_test_group(case["repair_tests"])
            ),
        },
        "tie_origin": {
            "cases_where_top_tie_is_single_coverage_class": sum(
                bool(item["top_tie_is_single_coverage_class"])
                for item in tie_origins
            ),
            "tie_groups": sum(item["tie_groups"] for item in tie_origins),
            "tie_groups_with_identical_coverage": sum(
                item["tie_groups_with_identical_coverage"] for item in tie_origins
            ),
        },
        "tie_statistics": {
            method: _tie_statistics(per_case, method) for method in METHODS
        },
    }
    FAULT_LOCALIZATION_INDEPENDENT_EVALUATION.parent.mkdir(
        parents=True, exist_ok=True
    )
    FAULT_LOCALIZATION_INDEPENDENT_EVALUATION.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation
