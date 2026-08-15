"""Build actual Pilot SBFL metrics and a research-oriented Markdown report."""

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_PILOT,
    FAULT_LOCALIZATION_EVALUATION,
    FAULT_LOCALIZATION_COVERAGE_ROOT,
    FAULT_LOCALIZATION_GROUND_TRUTH,
    FAULT_LOCALIZATION_RANKING_ROOT,
    FAULT_LOCALIZATION_REPORT,
)
from benchmark.models import load_case

from .algorithms import ALGORITHMS
from .evaluation import aggregate_metrics, evaluate_case
from .models import RankedLine


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {"min": 0, "median": 0, "mean": 0, "max": 0}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 2),
        "max": max(values),
    }


def build_evaluation() -> dict[str, Any]:
    ground_truth = {
        item["case_id"]: item
        for item in _load_jsonl(FAULT_LOCALIZATION_GROUND_TRUTH)
    }
    ranking_documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FAULT_LOCALIZATION_RANKING_ROOT.glob("*.json"))
    ]
    coverage_documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FAULT_LOCALIZATION_COVERAGE_ROOT.glob("*.json"))
    ]
    test_executions = [
        test for document in coverage_documents for test in document["tests"]
    ]
    status_counts = Counter(item["status"] for item in ranking_documents)
    per_case = []
    algorithm_case_metrics: dict[str, list[Any]] = {
        name: [] for name in ALGORITHMS
    }
    for document in ranking_documents:
        case_id = document["case_id"]
        fault_lines = tuple(ground_truth[case_id]["fault_lines"])
        algorithms: dict[str, Any] = {}
        for name in ALGORITHMS:
            ranking = tuple(
                RankedLine(**item) for item in document["rankings"].get(name, [])
            )
            metric = evaluate_case(ranking, fault_lines)
            algorithm_case_metrics[name].append(metric)
            fault_entries = [
                item for item in document["rankings"].get(name, [])
                if item["line"] in set(fault_lines)
            ]
            algorithms[name] = {
                "first_fault_rank": metric.first_fault_rank,
                "reciprocal_rank": metric.reciprocal_rank,
                "top_k": {str(k): value for k, value in metric.top_k.items()},
                "first_fault_entry": fault_entries[0] if fault_entries else None,
                "top_ranked_entry": (
                    document["rankings"][name][0]
                    if document["rankings"].get(name)
                    else None
                ),
            }
        per_case.append(
            {
                "case_id": case_id,
                "status": document["status"],
                "warnings": document.get("warnings", []),
                "passed_tests": document.get("passed_tests", 0),
                "failed_tests": document.get("failed_tests", 0),
                "executable_lines": document.get("executable_lines", 0),
                "ground_truth_fault_lines": list(fault_lines),
                "algorithms": algorithms,
            }
        )

    aggregate = {
        name: aggregate_metrics(metrics)
        for name, metrics in algorithm_case_metrics.items()
    }
    tie_statistics = {}
    for name in ALGORITHMS:
        top_ties = 0
        fault_ties = 0
        for case in per_case:
            algorithm = case["algorithms"][name]
            top = algorithm["top_ranked_entry"]
            fault = algorithm["first_fault_entry"]
            if top and top["tie_end_rank"] > top["tie_start_rank"]:
                top_ties += 1
            if fault and fault["tie_end_rank"] > fault["tie_start_rank"]:
                fault_ties += 1
        tie_statistics[name] = {
            "cases_with_top_score_tie": top_ties,
            "cases_with_fault_line_tied": fault_ties,
        }

    evaluation = {
        "pilot_cases": len(ranking_documents),
        "participating_cases": status_counts["localizable"],
        "not_localizable_cases": len(ranking_documents)
        - status_counts["localizable"],
        "not_localizable_reasons": {
            key: value
            for key, value in sorted(status_counts.items())
            if key != "localizable"
        },
        "cases_without_passing_repair_test": sum(
            "no_passing_repair_test" in item["warnings"] for item in per_case
        ),
        "repair_test_totals": {
            "passed": sum(item["passed_tests"] for item in per_case),
            "failed": sum(item["failed_tests"] for item in per_case),
            "total": sum(
                item["passed_tests"] + item["failed_tests"] for item in per_case
            ),
            "failed_with_zero_exit": sum(
                test["verdict"] == "FAIL" and test["exit_code"] == 0
                for test in test_executions
            ),
            "failed_with_nonzero_exit": sum(
                test["verdict"] == "FAIL"
                and test["exit_code"] not in (0, None)
                for test in test_executions
            ),
            "timed_out": sum(bool(test["timed_out"]) for test in test_executions),
        },
        "pass_tests_per_case": _distribution(
            [item["passed_tests"] for item in per_case]
        ),
        "fail_tests_per_case": _distribution(
            [item["failed_tests"] for item in per_case]
        ),
        "executable_lines_per_case": _distribution(
            [item["executable_lines"] for item in per_case]
        ),
        "metrics": aggregate,
        "tie_statistics": tie_statistics,
        "per_case": per_case,
    }
    FAULT_LOCALIZATION_EVALUATION.parent.mkdir(parents=True, exist_ok=True)
    FAULT_LOCALIZATION_EVALUATION.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation


def _percentage(value: float) -> str:
    return f"{value:.2%}"


def _algorithm_table(evaluation: dict[str, Any]) -> str:
    rows = []
    for name in ALGORITHMS:
        metric = evaluation["metrics"][name]
        rows.append(
            f"| {name} | {metric['top_1_hits']}/{metric['evaluated_cases']} "
            f"({_percentage(metric['top_1_accuracy'])}) | "
            f"{metric['top_3_hits']}/{metric['evaluated_cases']} "
            f"({_percentage(metric['top_3_accuracy'])}) | "
            f"{metric['top_5_hits']}/{metric['evaluated_cases']} "
            f"({_percentage(metric['top_5_accuracy'])}) | "
            f"{metric['top_10_hits']}/{metric['evaluated_cases']} "
            f"({_percentage(metric['top_10_accuracy'])}) | {metric['mrr']:.4f} |"
        )
    return "\n".join(rows)


def _case_analysis(case: dict[str, Any], success: bool) -> str:
    case_id = case["case_id"]
    benchmark_case = load_case(case_id, CODEFLAWS_PILOT)
    source_lines = benchmark_case.get_buggy_source().splitlines()
    fault_snippets = [
        f"L{line}: {source_lines[line - 1].strip()}"
        for line in case["ground_truth_fault_lines"]
        if 0 < line <= len(source_lines)
    ]
    lines = [
        f"### `{case_id}`",
        "",
        f"- Repair tests: {case['passed_tests']} PASS / {case['failed_tests']} FAIL; "
        f"executable lines: {case['executable_lines']}.",
        f"- Evaluation-only fault lines: {case['ground_truth_fault_lines']}.",
        f"- Buggy snippets: {'; '.join(fault_snippets) or '(unavailable)' }.",
    ]
    for name in ALGORITHMS:
        algorithm = case["algorithms"][name]
        fault = algorithm["first_fault_entry"]
        top = algorithm["top_ranked_entry"]
        if fault is None:
            lines.append(
                f"- {name}: miss; fault line is not in the gcov executable-line ranking. "
                f"Top line is L{top['line']} `{top['source_snippet']}` "
                f"with (ef, ep, nf, np)=({top['ef']}, {top['ep']}, {top['nf']}, {top['np']})."
            )
        else:
            lines.append(
                f"- {name}: first fault rank {fault['rank']}, score {fault['score']:.6g}, "
                f"spectrum ({fault['ef']}, {fault['ep']}, {fault['nf']}, {fault['np']}), "
                f"tie interval [{fault['tie_start_rank']}, {fault['tie_end_rank']}]."
            )
    if success:
        lines.append(
            "- Interpretation: failing-test coverage concentrates on the changed buggy-side "
            "line strongly enough to place it near the front, although its tie interval "
            "still shows how much ordering comes from the deterministic line-number rule."
        )
    else:
        ochiai = case["algorithms"]["ochiai"]
        if ochiai["first_fault_entry"] is None:
            lines.append(
                "- Interpretation: line-level gcov has no executable record for the diff "
                "ground truth, so no spectrum formula can rank that line. This is a "
                "representation mismatch, not an arithmetic failure."
            )
        else:
            lines.append(
                "- Interpretation: many lines share the same or stronger pass/fail coverage "
                "pattern. SBFL cannot distinguish their semantics, so the true line is "
                "pushed beyond Top-10 by ties and correlated execution."
            )
    return "\n".join(lines)


def render_report(evaluation: dict[str, Any]) -> str:
    cases = evaluation["per_case"]
    successful = sorted(
        (
            case
            for case in cases
            if case["passed_tests"] > 0
            and case["algorithms"]["ochiai"]["first_fault_rank"] is not None
            and case["algorithms"]["ochiai"]["first_fault_rank"] <= 3
        ),
        key=lambda case: (
            case["algorithms"]["ochiai"]["first_fault_rank"],
            case["case_id"],
        ),
    )[:2]
    failed = sorted(
        cases,
        key=lambda case: (
            case["algorithms"]["ochiai"]["first_fault_rank"] is not None,
            -(
                case["algorithms"]["ochiai"]["first_fault_rank"]
                if case["algorithms"]["ochiai"]["first_fault_rank"] is not None
                else 10**9
            ),
            case["case_id"],
        ),
    )[:2]
    repair = evaluation["repair_test_totals"]
    executable = evaluation["executable_lines_per_case"]
    pass_dist = evaluation["pass_tests_per_case"]
    fail_dist = evaluation["fail_tests_per_case"]
    tie_rows = "\n".join(
        f"| {name} | {value['cases_with_top_score_tie']} | "
        f"{value['cases_with_fault_line_tied']} |"
        for name, value in evaluation["tie_statistics"].items()
    )
    success_text = "\n\n".join(
        _case_analysis(case, True) for case in successful
    )
    failure_text = "\n\n".join(
        _case_analysis(case, False) for case in failed
    )
    return f"""# Codeflaws Pilot Spectrum-Based Fault Localization Report

This report is generated from saved per-test gcov matrices, suspicious-line rankings, and evaluation-only diff ground truth. Validation tests and reference coverage are not used by localization.

## Experiment Population

| Metric | Actual result |
| --- | ---: |
| Pilot cases | {evaluation['pilot_cases']} |
| Participating in SBFL | {evaluation['participating_cases']} |
| Not localizable | {evaluation['not_localizable_cases']} |
| Cases with no passing repair test | {evaluation['cases_without_passing_repair_test']} |
| Repair tests | {repair['total']} ({repair['passed']} PASS / {repair['failed']} FAIL) |
| FAIL execution modes | {repair['failed_with_zero_exit']} output mismatches with exit 0 / {repair['failed_with_nonzero_exit']} nonzero exits / {repair['timed_out']} timeouts |

All Pilot cases contain at least one failing repair test. Cases with no passing repair test remain mathematically localizable, but are marked because they provide no successful-execution contrast.

## Coverage Statistics

| Per-case measure | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: |
| PASS repair tests | {pass_dist['min']} | {pass_dist['median']} | {pass_dist['mean']} | {pass_dist['max']} |
| FAIL repair tests | {fail_dist['min']} | {fail_dist['median']} | {fail_dist['mean']} | {fail_dist['max']} |
| Executable source lines | {executable['min']} | {executable['median']} | {executable['mean']} | {executable['max']} |

Each repair test starts from a clean `.gcno` workspace in a fresh constrained Docker container. Its `.gcda` and gcov JSON are therefore test-local. Coverage builds inject a small signal handler with GCC `-include`; for fatal signals it calls `__gcov_dump()` and re-raises the same signal, preserving the runtime verdict while retaining pre-crash coverage.

## Algorithm Results

| Algorithm | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
{_algorithm_table(evaluation)}

Ochiai, Tarantula, and DStar2 have different numeric scales, but this Pilot's coarse spectra often induce the same ordering buckets. DStar2's zero denominator with `ef > 0` is represented by the largest finite IEEE-754 value so JSON remains standards-compliant.

## Ties And Top-K

Rankings sort by suspiciousness descending and line number ascending. `rank` is this deterministic position; every item also records `tie_start_rank` and `tie_end_rank`.

| Algorithm | Cases with top-score tie | Cases with tied fault line |
| --- | ---: | ---: |
{tie_rows}

A fault line tied across a Top-K boundary may be counted differently under another deterministic tie-break. The reported metrics use line-number ordering for reproducibility; they are not tie-aware best-case scores.

## Typical Successes

{success_text}

## Typical Failures

{failure_text}

## Comparison And Findings

- Coverage contrast is effective when the changed line is executable and is reached by failing tests more selectively than by passing tests.
- Correlated execution creates large tie groups. Formula changes cannot recover semantic distinctions absent from the spectrum.
- Ground-truth lines omitted from gcov executable records are guaranteed misses for statement-level SBFL and require a separately documented evaluation mapping if future work chooses to project them to executable neighbors.
- The 10 all-failing cases show why a failing test alone is insufficient for strong localization: Tarantula collapses covered failing lines to the same score when no passing execution exists.

## Scope And Limitations

The experiment covers 50 C defects under GCC/gcov 12.2.0. Ground truth comes from evaluation-only textual diff and is never passed to coverage, spectrum, formulas, or ranking. Results are sensitive to the Pilot tests, line-level gcov granularity, diff mapping, and deterministic handling of ties; they do not establish semantic causality.
"""


def write_report() -> dict[str, Any]:
    evaluation = build_evaluation()
    FAULT_LOCALIZATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    FAULT_LOCALIZATION_REPORT.write_text(
        render_report(evaluation), encoding="utf-8"
    )
    return evaluation
