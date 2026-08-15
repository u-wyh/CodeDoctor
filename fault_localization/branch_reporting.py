"""Evaluate line Ochiai against conservative branch tie-breaking."""

import json
import statistics
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_PILOT,
    FAULT_LOCALIZATION_BRANCH_EVALUATION,
    FAULT_LOCALIZATION_BRANCH_REPORT,
    FAULT_LOCALIZATION_COVERAGE_ROOT,
    FAULT_LOCALIZATION_GROUND_TRUTH,
    FAULT_LOCALIZATION_RANKING_ROOT,
)
from benchmark.models import load_case

from .evaluation import aggregate_metrics, evaluate_case
from .models import CoverageMatrix, RankedLine
from .tie_analysis import (
    branch_equivalence_classes,
    coverage_equivalence_classes,
    tie_group_sizes,
)


METHODS = ("ochiai", "ochiai_branch_tiebreak")
METHOD_LABELS = {
    "ochiai": "Original line Ochiai",
    "ochiai_branch_tiebreak": "Line Ochiai + branch tie-breaking",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _mean(values: list[int | float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _fault_entries(
    ranking: tuple[RankedLine, ...], fault_lines: tuple[int, ...]
) -> list[RankedLine]:
    faults = set(fault_lines)
    return [item for item in ranking if item.line in faults]


def _line_vectors(matrix: CoverageMatrix) -> dict[int, tuple[int, ...]]:
    return {
        line: tuple(int(line in test.covered_lines) for test in matrix.tests)
        for line in matrix.executable_lines
    }


def _tie_origin(
    ranking: tuple[RankedLine, ...], vectors: dict[int, tuple[int, ...]]
) -> dict[str, int | bool]:
    groups: dict[tuple[int, int], list[int]] = {}
    for item in ranking:
        groups.setdefault(
            (item.tie_start_rank, item.tie_end_rank), []
        ).append(item.line)
    tied = [lines for lines in groups.values() if len(lines) > 1]
    identical = [
        lines for lines in tied if len({vectors[line] for line in lines}) == 1
    ]
    top = groups.get((ranking[0].tie_start_rank, ranking[0].tie_end_rank), []) if ranking else []
    return {
        "tie_groups": len(tied),
        "tie_groups_with_identical_coverage": len(identical),
        "tied_lines": sum(len(lines) for lines in tied),
        "identical_coverage_tied_lines": sum(len(lines) for lines in identical),
        "top_tie_is_single_coverage_class": (
            len(top) > 1 and len({vectors[line] for line in top}) == 1
        ),
    }


def build_branch_evaluation() -> dict[str, Any]:
    ground_truth = {
        item["case_id"]: tuple(item["fault_lines"])
        for item in _load_jsonl(FAULT_LOCALIZATION_GROUND_TRUTH)
    }
    method_metrics: dict[str, list[Any]] = {name: [] for name in METHODS}
    per_case = []
    coverage_paths = sorted(FAULT_LOCALIZATION_COVERAGE_ROOT.glob("*.json"))
    for coverage_path in coverage_paths:
        matrix = CoverageMatrix.from_dict(_load_json(coverage_path))
        ranking_document = _load_json(
            FAULT_LOCALIZATION_RANKING_ROOT / coverage_path.name
        )
        fault_lines = ground_truth[matrix.case_id]
        vectors = _line_vectors(matrix)
        classes = coverage_equivalence_classes(matrix)
        class_sizes = {
            line: len(group.lines) for group in classes for line in group.lines
        }
        branch_classes = branch_equivalence_classes(matrix)
        method_data: dict[str, Any] = {}
        for method in METHODS:
            ranking = tuple(
                RankedLine(**item)
                for item in ranking_document["rankings"].get(method, [])
            )
            metric = evaluate_case(ranking, fault_lines)
            method_metrics[method].append(metric)
            faults = _fault_entries(ranking, fault_lines)
            top = ranking[0] if ranking else None
            sizes = tie_group_sizes(ranking)
            method_data[method] = {
                "metric": asdict(metric),
                "first_fault_entry": asdict(faults[0]) if faults else None,
                "top_ranked_entry": asdict(top) if top else None,
                "unique_scores": len(
                    {
                        (item.score, item.branch_score)
                        if method == "ochiai_branch_tiebreak"
                        else (item.score,)
                        for item in ranking
                    }
                ),
                "max_tie_size": max(sizes, default=0),
                "average_tie_size": _mean(list(sizes)),
                "tie_origin": _tie_origin(ranking, vectors),
            }

        original_metric = method_data["ochiai"]["metric"]
        branch_metric = method_data["ochiai_branch_tiebreak"]["metric"]
        original_average = original_metric["average_fault_rank"]
        branch_average = branch_metric["average_fault_rank"]
        per_case.append(
            {
                "case_id": matrix.case_id,
                "status": ranking_document["status"],
                "warnings": ranking_document.get("warnings", []),
                "passed_tests": matrix.passed_tests,
                "failed_tests": matrix.failed_tests,
                "test_ids": [test.test_id for test in matrix.tests],
                "test_verdicts": [test.verdict.value for test in matrix.tests],
                "executable_lines": len(matrix.executable_lines),
                "unique_line_coverage_vectors": len(classes),
                "unique_line_spectrum_patterns": len(
                    {
                        (item["ef"], item["ep"], item["nf"], item["np"])
                        for item in ranking_document["spectrum"]
                    }
                ),
                "max_coverage_equivalence_class_size": max(
                    (len(group.lines) for group in classes), default=0
                ),
                "average_coverage_equivalence_class_size": _mean(
                    [len(group.lines) for group in classes]
                ),
                "fault_coverage_equivalence_class_sizes": {
                    str(line): class_sizes.get(line)
                    for line in fault_lines
                },
                "branch_outcomes": len(matrix.executable_branches),
                "unique_branch_coverage_vectors": len(branch_classes),
                "ground_truth_fault_lines": list(fault_lines),
                "line_coverage_vectors": {
                    str(line): list(vector) for line, vector in vectors.items()
                },
                "methods": method_data,
                "average_rank_improvement": (
                    original_average - branch_average
                    if original_average is not None and branch_average is not None
                    else 0.0
                ),
            }
        )

    metrics = {
        name: aggregate_metrics(values) for name, values in method_metrics.items()
    }
    tie_statistics = {}
    for method in METHODS:
        values = [case["methods"][method] for case in per_case]
        tie_statistics[method] = {
            "cases_with_top_score_tie": sum(
                item["top_ranked_entry"] is not None
                and item["top_ranked_entry"]["tie_end_rank"]
                > item["top_ranked_entry"]["tie_start_rank"]
                for item in values
            ),
            "cases_with_fault_line_tied": sum(
                item["metric"]["fault_tie_size"] is not None
                and item["metric"]["fault_tie_size"] > 1
                for item in values
            ),
            "average_max_tie_size": _mean(
                [item["max_tie_size"] for item in values]
            ),
            "average_score_group_size": _mean(
                [item["average_tie_size"] for item in values]
            ),
            "average_unique_scores": _mean(
                [item["unique_scores"] for item in values]
            ),
            "average_fault_tie_size": _mean(
                [
                    item["metric"]["fault_tie_size"]
                    for item in values
                    if item["metric"]["fault_tie_size"] is not None
                ]
            ),
        }

    original_origins = [case["methods"]["ochiai"]["tie_origin"] for case in per_case]
    evaluation = {
        "pilot_cases": len(per_case),
        "repair_tests": sum(
            case["passed_tests"] + case["failed_tests"] for case in per_case
        ),
        "passed_tests": sum(case["passed_tests"] for case in per_case),
        "failed_tests": sum(case["failed_tests"] for case in per_case),
        "methods": list(METHODS),
        "metrics": metrics,
        "tie_statistics": tie_statistics,
        "coverage_equivalence": {
            "executable_lines": sum(case["executable_lines"] for case in per_case),
            "unique_vectors": sum(
                case["unique_line_coverage_vectors"] for case in per_case
            ),
            "average_unique_vectors_per_case": _mean(
                [case["unique_line_coverage_vectors"] for case in per_case]
            ),
            "average_unique_spectrum_patterns_per_case": _mean(
                [case["unique_line_spectrum_patterns"] for case in per_case]
            ),
            "average_max_class_size": _mean(
                [case["max_coverage_equivalence_class_size"] for case in per_case]
            ),
            "largest_class_size": max(
                (case["max_coverage_equivalence_class_size"] for case in per_case),
                default=0,
            ),
            "average_fault_class_size": _mean(
                [
                    size
                    for case in per_case
                    for size in case["fault_coverage_equivalence_class_sizes"].values()
                    if size is not None
                ]
            ),
            "fault_lines_with_executable_coverage": sum(
                size is not None
                for case in per_case
                for size in case["fault_coverage_equivalence_class_sizes"].values()
            ),
            "branch_outcomes": sum(case["branch_outcomes"] for case in per_case),
            "unique_branch_vectors": sum(
                case["unique_branch_coverage_vectors"] for case in per_case
            ),
            "average_unique_branch_vectors_per_case": _mean(
                [case["unique_branch_coverage_vectors"] for case in per_case]
            ),
        },
        "tie_origin": {
            "tie_groups": sum(item["tie_groups"] for item in original_origins),
            "tie_groups_with_identical_coverage": sum(
                item["tie_groups_with_identical_coverage"]
                for item in original_origins
            ),
            "cases_where_top_tie_is_single_coverage_class": sum(
                bool(item["top_tie_is_single_coverage_class"])
                for item in original_origins
            ),
        },
        "cases_with_average_rank_improvement": sum(
            case["average_rank_improvement"] > 0 for case in per_case
        ),
        "cases_with_average_rank_regression": sum(
            case["average_rank_improvement"] < 0 for case in per_case
        ),
        "per_case": per_case,
    }
    FAULT_LOCALIZATION_BRANCH_EVALUATION.parent.mkdir(parents=True, exist_ok=True)
    FAULT_LOCALIZATION_BRANCH_EVALUATION.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evaluation


def _percent(value: float) -> str:
    return f"{value:.2%}"


def _metric_row(name: str, metric: dict[str, Any]) -> str:
    return (
        f"| {METHOD_LABELS[name]} | {_percent(metric['top_1_accuracy'])} | "
        f"{_percent(metric['top_3_accuracy'])} | "
        f"{_percent(metric['top_5_accuracy'])} | "
        f"{_percent(metric['top_10_accuracy'])} | {metric['mrr']:.4f} |"
    )


def _tie_metric_rows(name: str, metric: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"| {METHOD_LABELS[name]} | {mode.replace('_', ' ')} | "
            f"{_percent(values['top_1_accuracy'])} | "
            f"{_percent(values['top_3_accuracy'])} | "
            f"{_percent(values['top_5_accuracy'])} | "
            f"{_percent(values['top_10_accuracy'])} | {values['mrr']:.4f} |"
        )
        for mode, values in metric["tie_aware"].items()
    )


def _case_detail(case: dict[str, Any], improved: bool) -> str:
    case_id = case["case_id"]
    benchmark_case = load_case(case_id, CODEFLAWS_PILOT)
    source_lines = benchmark_case.get_buggy_source().splitlines()
    fault_lines = set(case["ground_truth_fault_lines"])
    context_lines = sorted(
        {
            line
            for fault in fault_lines
            for line in range(max(1, fault - 2), min(len(source_lines), fault + 2) + 1)
        }
    )
    source = "\n".join(
        (
            f"{line:4d}{' *' if line in fault_lines else '  '} "
            f"{source_lines[line - 1]}"
        ).rstrip()
        for line in context_lines
    )
    coverage = CoverageMatrix.from_dict(
        _load_json(FAULT_LOCALIZATION_COVERAGE_ROOT / f"{case_id}.json")
    )
    ranking = _load_json(FAULT_LOCALIZATION_RANKING_ROOT / f"{case_id}.json")
    original = case["methods"]["ochiai"]
    branch = case["methods"]["ochiai_branch_tiebreak"]
    original_fault = original["first_fault_entry"]
    branch_fault = branch["first_fault_entry"]
    original_group = {
        item["line"]
        for item in ranking["rankings"]["ochiai"]
        if original_fault
        and item["tie_start_rank"] == original_fault["tie_start_rank"]
        and item["tie_end_rank"] == original_fault["tie_end_rank"]
    }
    fault_branch_score = (
        branch_fault["branch_score"] if branch_fault is not None else None
    )
    group_branch_scores = [
        branch_by_line["branch_score"]
        for branch_by_line in ranking["rankings"]["ochiai_branch_tiebreak"]
        if branch_by_line["line"] in original_group
    ]
    evidence_lines = sorted(original_group | fault_lines)[:16]
    line_rows = []
    original_by_line = {
        item["line"]: item for item in ranking["rankings"]["ochiai"]
    }
    branch_by_line = {
        item["line"]: item
        for item in ranking["rankings"]["ochiai_branch_tiebreak"]
    }
    vectors = case["line_coverage_vectors"]
    for line in evidence_lines:
        if line not in original_by_line:
            continue
        before = original_by_line[line]
        after = branch_by_line[line]
        line_rows.append(
            f"| {'yes' if line in fault_lines else ''} | L{line} | "
            f"`{''.join(map(str, vectors[str(line)]))}` | {before['score']:.4f} | "
            f"{(after['branch_score'] or 0.0):.4f} | {before['rank']} | {after['rank']} |"
        )
    branch_rows = []
    branch_spectrum = {
        (item["line"], item["branch_index"]): item
        for item in ranking.get("branch_spectrum", [])
    }
    for line in evidence_lines:
        keys = sorted(key for key in coverage.executable_branches if key[0] == line)
        for key in keys:
            taken_vector = []
            counts = []
            for test in coverage.tests:
                outcome = next(
                    branch
                    for branch in test.branches
                    if (branch.line, branch.branch_index) == key
                )
                taken_vector.append(int(outcome.taken))
                counts.append(outcome.count)
            spectrum = branch_spectrum[key]
            branch_rows.append(
                f"| L{key[0]} b{key[1]} | `{' '.join(map(str, taken_vector))}` | "
                f"`{' '.join(map(str, counts))}` | "
                f"({spectrum['ef']},{spectrum['ep']},{spectrum['nf']},{spectrum['np']}) | "
                f"{spectrum['score']:.4f} |"
            )
    verdicts = ", ".join(
        f"`{test.test_id}`={test.verdict.value}" for test in coverage.tests
    )
    if original_fault is None:
        explanation = (
            "The diff ground truth has no executable gcov line, so neither line nor "
            "branch evidence can rank it."
        )
    elif improved:
        lower = sum(
            score < fault_branch_score
            for score in group_branch_scores
            if score is not None and fault_branch_score is not None
        )
        explanation = (
            f"The fault's max branch score is {fault_branch_score:.4f}; it exceeds "
            f"{lower} lines inside the original {len(original_group)}-line tie, "
            "so its uncertainty interval contracts."
        )
    elif fault_branch_score in (None, 0.0):
        explanation = (
            "The fault line has no failing-correlated branch outcome, so branch "
            "evidence cannot lift it inside the original line-score tie."
        )
    else:
        higher = sum(
            score > fault_branch_score
            for score in group_branch_scores
            if score is not None
        )
        explanation = (
            f"The fault's max branch score is {fault_branch_score:.4f}, while "
            f"{higher} lines in its original tie have stronger branch evidence; "
            "the conservative tie-break therefore provides no fault-rank gain."
        )
    branch_table = "\n".join(branch_rows) or "| none | - | - | - | - |"
    return f"""### `{case_id}`

Repair-test verdicts: {verdicts}.

```c
{source}
```

`*` marks evaluation-only diff ground truth. The line vector follows the repair-test order shown above.

| Fault | Line | Line coverage vector | Line Ochiai | Max branch Ochiai | Original rank | Branch-aware rank |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
{chr(10).join(line_rows)}

| Branch outcome | Taken vector | Execution counts | (ef,ep,nf,np) | Ochiai |
| --- | --- | --- | --- | ---: |
{branch_table}

Original fault tie interval: `{None if original_fault is None else [original_fault['tie_start_rank'], original_fault['tie_end_rank']]}`; branch-aware interval: `{None if branch_fault is None else [branch_fault['tie_start_rank'], branch_fault['tie_end_rank']]}`. {explanation} Branch evidence can only separate lines whose branch-outcome spectra differ; lines without branch records or with identical branch vectors remain indistinguishable.
"""


def render_branch_report(evaluation: dict[str, Any]) -> str:
    metrics = evaluation["metrics"]
    tie = evaluation["tie_statistics"]
    equivalence = evaluation["coverage_equivalence"]
    improved = sorted(
        (
            case for case in evaluation["per_case"]
            if case["average_rank_improvement"] > 0
        ),
        key=lambda case: (-case["average_rank_improvement"], case["case_id"]),
    )[:2]
    missing = sorted(
        (
            case for case in evaluation["per_case"]
            if case["methods"]["ochiai"]["metric"]["average_fault_rank"] is None
        ),
        key=lambda case: case["case_id"],
    )[:1]
    reachable_without_gain = sorted(
        (
            case for case in evaluation["per_case"]
            if case["average_rank_improvement"] <= 0
            and case["methods"]["ochiai"]["metric"]["average_fault_rank"] is not None
        ),
        key=lambda case: (-case["average_rank_improvement"], case["case_id"]),
    )[:1]
    unchanged = missing + reachable_without_gain
    tie_rows = "\n".join(
        f"| {METHOD_LABELS[name]} | {values['cases_with_top_score_tie']} | "
        f"{values['average_unique_scores']:.2f} | "
        f"{values['average_score_group_size']:.2f} | "
        f"{values['average_max_tie_size']:.2f} | "
        f"{values['cases_with_fault_line_tied']} | "
        f"{values['average_fault_tie_size']:.2f} |"
        for name, values in tie.items()
    )
    tie_origin = evaluation["tie_origin"]
    identical_share = (
        tie_origin["tie_groups_with_identical_coverage"]
        / tie_origin["tie_groups"]
        if tie_origin["tie_groups"]
        else 0.0
    )
    return f"""# Branch-Aware Fault Localization on the Codeflaws Pilot

## Research Question

Does real branch-outcome execution evidence reduce the ambiguity of line-level SBFL? This experiment uses the same 50 buggy programs and 180 repair tests as Phase 4. Reference programs, validation tests, and diff ground truth are excluded from collection and ranking; diff ground truth enters only this evaluation.

## Why Phase 4 Produced Ties

Across {equivalence['executable_lines']} executable line records, only {equivalence['unique_vectors']} distinct per-case line coverage vectors exist. A case has {equivalence['average_unique_vectors_per_case']:.2f} unique vectors and {equivalence['average_unique_spectrum_patterns_per_case']:.2f} unique `(ef, ep, nf, np)` patterns on average. Its largest equivalence class averages {equivalence['average_max_class_size']:.2f} lines and reaches {equivalence['largest_class_size']} lines. The {equivalence['fault_lines_with_executable_coverage']} executable fault lines belong to classes of {equivalence['average_fault_class_size']:.2f} lines on average.

Of {tie_origin['tie_groups']} original Ochiai tie groups, {tie_origin['tie_groups_with_identical_coverage']} ({identical_share:.2%}) consist entirely of one coverage equivalence class. In {tie_origin['cases_where_top_tie_is_single_coverage_class']} cases the complete highest-score tie is one class. Thus most ambiguity is already present in the line coverage vectors; the Ochiai formula also merges some distinct vectors that have equal `(ef, ep, nf, np)` counts.

Ten cases have no passing repair test, and many cases have only a handful of repair tests. Co-executed statements therefore receive identical vectors, especially along straight-line regions near the fault.

## Method

GCC 12.2/gcov emits each source line's branch arcs under `--branch-probabilities --branch-counts`. Every repair test runs from a clean `.gcno` workspace, so the saved count and taken state are test-local. The experiment observes {equivalence['branch_outcomes']} per-case branch outcomes and {equivalence['unique_branch_vectors']} branch coverage vectors ({equivalence['average_unique_branch_vectors_per_case']:.2f} unique vectors per case on average). Each branch outcome receives an `(ef, ep, nf, np)` spectrum and Ochiai score. A source line's branch evidence is the maximum score among its outcomes.

The branch-aware method sorts lexicographically by `(line Ochiai, max branch Ochiai)`. Branch evidence therefore breaks only exact line-score ties and cannot reverse an ordering established by line Ochiai. No parameter is trained on Pilot ground truth.

## Deterministic Metrics

| Method | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(_metric_row(name, metrics[name]) for name in METHODS)}

## Tie-Aware Metrics

Optimistic uses a tie's best rank, pessimistic its worst rank, and average-rank uses the interval midpoint. These expose uncertainty hidden by line-number ordering.

| Method | Tie policy | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(_tie_metric_rows(name, metrics[name]) for name in METHODS)}

## Ambiguity

| Method | Top-score tie cases | Avg unique score keys | Avg score-group size | Avg maximum tie | Tied-fault cases | Avg fault tie |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{tie_rows}

Branch tie-breaking improves average tie-aware fault rank in {evaluation['cases_with_average_rank_improvement']} cases and regresses it in {evaluation['cases_with_average_rank_regression']} cases. A reduction in generic tie counts does not automatically imply better fault ranking: branch evidence may distinguish nonfaulty lines first or may be absent on the changed statement.

The average-rank policy is the most useful central estimate here: its MRR rises from {metrics['ochiai']['tie_aware']['average_rank']['mrr']:.4f} to {metrics['ochiai_branch_tiebreak']['tie_aware']['average_rank']['mrr']:.4f}, while pessimistic MRR rises from {metrics['ochiai']['tie_aware']['pessimistic']['mrr']:.4f} to {metrics['ochiai_branch_tiebreak']['tie_aware']['pessimistic']['mrr']:.4f}. Optimistic MRR falls from {metrics['ochiai']['tie_aware']['optimistic']['mrr']:.4f} to {metrics['ochiai_branch_tiebreak']['tie_aware']['optimistic']['mrr']:.4f}: splitting a broad tie removes the unearned assumption that its fault can always occupy the best slot. The deterministic Top-K and MRR gains are therefore accompanied by stronger average and worst-case tie-aware results, not merely a favorable line-number order.

## Cases Where Branch Evidence Helps

{chr(10).join(_case_detail(case, True) for case in improved) if improved else 'No Pilot case showed a positive average-rank change.'}

## Cases Where Branch Evidence Does Not Help

{chr(10).join(_case_detail(case, False) for case in unchanged)}

## Meaning for Later Repair

The conservative tie-break produces a more honest candidate order when failing and passing executions choose different branch outcomes inside a line-score tie. It cannot add semantic evidence to straight-line statements, non-executable diff lines, or branch outcomes that all repair tests exercise identically. A later repair component should preserve tie intervals and equivalence-class context instead of treating a deterministic line number as certainty.

## Limitations

This is a single 50-case Pilot under one GCC/gcov version. Repair suites are small, ten cases lack a PASS execution, and textual diff lines are an imperfect fault oracle. Branch arcs are compiler-generated control-flow outcomes rather than source-level predicate truth values, and max aggregation may emphasize one exceptional arc. The experiment tests ambiguity reduction, not causal fault identification or cross-dataset generalization.
"""


def write_branch_report() -> dict[str, Any]:
    evaluation = build_branch_evaluation()
    FAULT_LOCALIZATION_BRANCH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    FAULT_LOCALIZATION_BRANCH_REPORT.write_text(
        render_branch_report(evaluation), encoding="utf-8"
    )
    return evaluation
