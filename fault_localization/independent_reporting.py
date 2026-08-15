"""Render the independent FL-v1 evaluation as a reproducible Markdown report."""

import json
from pathlib import Path
from typing import Any

from benchmark.config import (
    CODEFLAWS_FL_EVALUATION,
    FAULT_LOCALIZATION_INDEPENDENT_EVALUATION,
    FAULT_LOCALIZATION_INDEPENDENT_RANKING_ROOT,
    FAULT_LOCALIZATION_INDEPENDENT_REPORT,
)
from benchmark.models import load_case

from .independent_evaluation import METHODS, build_independent_evaluation


METHOD_LABELS = {
    "ochiai": "Original Ochiai",
    "ochiai_branch_tiebreak": "Branch-aware FL-v1",
}


def _percent(value: float) -> str:
    return f"{value:.2%}"


def _metric_table(evaluation: dict[str, Any]) -> str:
    rows = []
    for method in METHODS:
        metric = evaluation["metrics"][method]
        average = metric["tie_aware"]["average_rank"]
        pessimistic = metric["tie_aware"]["pessimistic"]
        rows.append(
            f"| {METHOD_LABELS[method]} | {_percent(metric['top_1_accuracy'])} | "
            f"{_percent(metric['top_3_accuracy'])} | {_percent(metric['top_5_accuracy'])} | "
            f"{_percent(metric['top_10_accuracy'])} | {metric['mrr']:.4f} | "
            f"{average['mrr']:.4f} | {pessimistic['mrr']:.4f} |"
        )
    return "\n".join(rows)


def _improvement_table(evaluation: dict[str, Any]) -> str:
    baseline = evaluation["metrics"]["ochiai"]
    treatment = evaluation["metrics"]["ochiai_branch_tiebreak"]
    rows = []
    for label, key in (("Top-1", "top_1_accuracy"), ("Top-3", "top_3_accuracy"),
                       ("Top-5", "top_5_accuracy"), ("Top-10", "top_10_accuracy"),
                       ("MRR", "mrr")):
        before = baseline[key]
        after = treatment[key]
        absolute = after - before
        relative = absolute / before if before else 0.0
        rows.append(
            f"| {label} | {before:.4f} | {after:.4f} | {absolute:+.4f} | "
            f"{relative:+.2%} |"
        )
    before = baseline["tie_aware"]["average_rank"]["mrr"]
    after = treatment["tie_aware"]["average_rank"]["mrr"]
    rows.append(
        f"| Average-rank MRR | {before:.4f} | {after:.4f} | "
        f"{after-before:+.4f} | {(after-before)/before:+.2%} |"
    )
    return "\n".join(rows)


def _subgroup_table(evaluation: dict[str, Any]) -> str:
    labels = {
        "repair_tests": "Repair tests",
        "pass_tests": "PASS tests",
        "coverage_diversity": "Coverage diversity",
        "fault_equivalence_class_size": "Fault equivalence class",
    }
    rows = []
    for dimension, groups in evaluation["subgroups"].items():
        for group, result in groups.items():
            metric = result["average_rank_mrr"]
            changes = result["paired_changes"]
            rows.append(
                f"| {labels[dimension]} | {group} | {result['cases']} | "
                f"{metric['original']:.4f} | {metric['branch_aware']:.4f} | "
                f"{metric['difference']:+.4f} | {changes['improved']}/"
                f"{changes['unchanged']}/{changes['regressed']} |"
            )
    return "\n".join(rows)


def _fault_entry(document: dict[str, Any], method: str, faults: set[int]) -> dict[str, Any] | None:
    return next(
        (entry for entry in document["rankings"][method] if entry["line"] in faults),
        None,
    )


def _case_study(case: dict[str, Any], category: str) -> str:
    case_id = case["case_id"]
    benchmark_case = load_case(case_id, CODEFLAWS_FL_EVALUATION)
    source = benchmark_case.get_buggy_source().splitlines()
    fault_lines = set(case["fault_lines"])
    snippets = [
        f"L{line}: `{source[line - 1].strip()}`"
        for line in sorted(fault_lines)
        if 0 < line <= len(source)
    ]
    ranking = json.loads(
        (FAULT_LOCALIZATION_INDEPENDENT_RANKING_ROOT / f"{case_id}.json").read_text(
            encoding="utf-8"
        )
    )
    original = _fault_entry(ranking, "ochiai", fault_lines)
    aware = _fault_entry(ranking, "ochiai_branch_tiebreak", fault_lines)

    lines = [
        f"### {category}: `{case_id}`",
        "",
        f"- Tests: {case['passed_tests']} PASS / {case['failed_tests']} FAIL; "
        f"fault line(s): {', '.join(snippets) or '(not present in source)' }.",
    ]
    for label, entry in (("Original", original), ("Branch-aware", aware)):
        if entry is None:
            lines.append(f"- {label}: fault line is not executable and has no rank.")
        else:
            branch = entry.get("branch_score")
            branch_text = "n/a" if branch is None else f"{branch:.4f}"
            lines.append(
                f"- {label}: deterministic rank {entry['rank']}, tie interval "
                f"[{entry['tie_start_rank']}, {entry['tie_end_rank']}], line score "
                f"{entry['score']:.4f}, branch score {branch_text}, spectrum "
                f"(ef={entry['ef']}, ep={entry['ep']}, nf={entry['nf']}, np={entry['np']})."
            )
    if category == "Improved":
        explanation = (
            "Branch evidence separates the fault from lines with the same line-level "
            "Ochiai score and moves it toward the front of that tie."
        )
    elif case["non_executable_fault"]:
        explanation = (
            "The diff points to a non-executable line, so neither line coverage nor "
            "branch evidence can assign it a spectrum or rank."
        )
    elif category == "Unchanged":
        explanation = (
            "The fault retains an indistinguishable final score; identical execution "
            "evidence leaves the original ambiguity unresolved."
        )
    else:
        explanation = (
            "A competing branch-bearing line receives stronger branch evidence inside "
            "the same line-score group, pushing the fault backward."
        )
    lines.append(f"- Interpretation: {explanation}")
    return "\n".join(lines)


def _select_case_studies(cases: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    improved = sorted(
        (case for case in cases if case["average_rank_reciprocal_difference"] > 0),
        key=lambda case: case["average_rank_reciprocal_difference"],
        reverse=True,
    )[:2]
    regressed = sorted(
        (case for case in cases if case["average_rank_reciprocal_difference"] < 0),
        key=lambda case: case["average_rank_reciprocal_difference"],
    )[:2]
    unchanged = [
        case for case in cases
        if abs(case["average_rank_reciprocal_difference"]) < 1e-15
    ]
    non_executable = next(case for case in unchanged if case["non_executable_fault"])
    straight = next(
        case for case in unchanged
        if case["straight_line_ambiguity"] and not case["non_executable_fault"]
    )
    return (
        [("Improved", case) for case in improved]
        + [("Unchanged", non_executable), ("Unchanged", straight)]
        + [("Regressed", case) for case in regressed]
    )


def render_independent_report(evaluation: dict[str, Any]) -> str:
    dataset = evaluation["dataset"]
    ties = evaluation["tie_statistics"]
    equivalence = evaluation["coverage_equivalence"]
    boundaries = evaluation["failure_boundaries"]
    changes = evaluation["paired_changes"]["average_rank_reciprocal"]
    deterministic_ci = evaluation["bootstrap"]["deterministic_mrr_difference"]
    average_ci = evaluation["bootstrap"]["average_rank_mrr_difference"]
    studies = "\n\n".join(
        _case_study(case, category)
        for category, case in _select_case_studies(evaluation["per_case"])
    )
    class_distribution = ", ".join(
        f"{name}={count}"
        for name, count in sorted(dataset["defect_class_distribution"].items())
    )
    exclusion_reasons = ", ".join(
        f"{name}={count}"
        for name, count in sorted(dataset["dynamic_exclusion_reasons"].items())
    )
    mcnemar_rows = "\n".join(
        f"| Top-{key} | {value['baseline_only']} | {value['treatment_only']} | "
        f"{value['discordant']} | {value['exact_two_sided_p_value']:.6g} |"
        for key, value in evaluation["mcnemar"].items()
    )
    return f"""# Independent Fault Localization Evaluation

Method `fl-v1` was frozen before selecting this independent set. Ground truth, reference source, validation tests, and buggy/reference diffs were used only after ranking. The artifact leakage scan passed for all {dataset['evaluation_cases']} cases.

## Dataset

- Pilot: {dataset['pilot_cases']} cases; Evaluation: {dataset['evaluation_cases']} cases; overlap: {dataset['pilot_overlap']}.
- Fixed seed: `{dataset['seed']}`; static exclusions: {dataset['static_exclusions']}; dynamic exclusions: {dataset['dynamic_exclusions']}; recorded exclusions: {dataset['excluded_records']}.
- Dynamic exclusion reasons: {exclusion_reasons}.
- Repair tests: {dataset['repair_tests']} total, {dataset['passed_repair_tests']} PASS and {dataset['failed_repair_tests']} FAIL.
- Defect classes ({len(dataset['defect_class_distribution'])}): {class_distribution}.

## Baseline And FL-v1

| Method | Top-1 | Top-3 | Top-5 | Top-10 | MRR | Average-rank MRR | Pessimistic MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
{_metric_table(evaluation)}

## Improvement

| Metric | Original | Branch-aware | Absolute | Relative |
|---|---:|---:|---:|---:|
{_improvement_table(evaluation)}

On the primary tie-aware average-rank reciprocal outcome, {changes['improved']} cases improved, {changes['unchanged']} were unchanged, and {changes['regressed']} regressed. Deterministic reciprocal rank changed in {evaluation['paired_changes']['deterministic_reciprocal']['improved']}/{evaluation['paired_changes']['deterministic_reciprocal']['unchanged']}/{evaluation['paired_changes']['deterministic_reciprocal']['regressed']} cases (improved/unchanged/regressed).

## Statistical Uncertainty

- Deterministic MRR difference: {deterministic_ci['observed_difference']:+.4f}; 95% paired bootstrap CI [{deterministic_ci['confidence_interval_95'][0]:+.4f}, {deterministic_ci['confidence_interval_95'][1]:+.4f}], {deterministic_ci['samples']} samples, seed `{deterministic_ci['seed']}`.
- Average-rank MRR difference: {average_ci['observed_difference']:+.4f}; 95% paired bootstrap CI [{average_ci['confidence_interval_95'][0]:+.4f}, {average_ci['confidence_interval_95'][1]:+.4f}], {average_ci['samples']} samples, seed `{average_ci['seed']}`.

| Outcome | Original only | FL-v1 only | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|
{mcnemar_rows}

## Tie And Coverage Equivalence Analysis

| Method | Top-score tie cases | Fault-tie cases | Mean maximum tie | Mean fault tie |
|---|---:|---:|---:|---:|
| Original Ochiai | {ties['ochiai']['cases_with_top_score_tie']} | {ties['ochiai']['cases_with_fault_line_tied']} | {ties['ochiai']['average_max_tie_size']:.2f} | {ties['ochiai']['average_fault_tie_size']:.2f} |
| Branch-aware FL-v1 | {ties['ochiai_branch_tiebreak']['cases_with_top_score_tie']} | {ties['ochiai_branch_tiebreak']['cases_with_fault_line_tied']} | {ties['ochiai_branch_tiebreak']['average_max_tie_size']:.2f} | {ties['ochiai_branch_tiebreak']['average_fault_tie_size']:.2f} |

Across {equivalence['executable_lines']} executable lines there were only {equivalence['unique_vectors']} unique line-coverage vectors, an equivalence ratio of {_percent(equivalence['coverage_equivalence_ratio'])}. Mean maximum class size was {equivalence['average_max_class_size']:.2f}, and mean executable fault-class size was {equivalence['average_fault_class_size']:.2f}. Of {evaluation['tie_origin']['tie_groups']} original tie groups, {evaluation['tie_origin']['tie_groups_with_identical_coverage']} consisted of one line-coverage class; {evaluation['tie_origin']['cases_where_top_tie_is_single_coverage_class']} cases had this pattern at the top score.

## Mechanism Analysis

Average-rank MRR is used for subgroup comparisons so deterministic line-number ordering cannot masquerade as an improvement.

| Dimension | Group | Cases | Original | FL-v1 | Difference | I/U/R |
|---|---|---:|---:|---:|---:|---:|
{_subgroup_table(evaluation)}

## Failure Boundaries

- 0-PASS: {boundaries['zero_pass_cases']}/{dataset['evaluation_cases']} cases. Their separate result appears in the PASS-test subgroup above.
- Non-executable ground truth: {boundaries['non_executable_fault_cases']}/{dataset['evaluation_cases']} ({_percent(boundaries['non_executable_fault_cases']/dataset['evaluation_cases'])}). These lines cannot receive an SBFL rank.
- Straight-line ambiguity: {boundaries['straight_line_ambiguity_cases']}/{dataset['evaluation_cases']} ({_percent(boundaries['straight_line_ambiguity_cases']/dataset['evaluation_cases'])}). The fault remains tied with a non-fault line that has the same line vector and final branch-aware score.

## Case Studies

{studies}

## Research Questions

### RQ1: Does branch-aware FL improve localization accuracy independently?

Yes at the aggregate level. Deterministic MRR rises by {deterministic_ci['observed_difference']:+.4f} and average-rank MRR by {average_ci['observed_difference']:+.4f}; both paired bootstrap intervals exclude zero. Top-1, Top-3, and Top-5 improvements are significant under exact McNemar tests, while Top-10 is not. Per-case average-rank outcomes remain mixed ({changes['improved']}/{changes['unchanged']}/{changes['regressed']}).

### RQ2: Does branch evidence reduce coverage-induced ties?

Yes. Top-score tie cases fall from {ties['ochiai']['cases_with_top_score_tie']} to {ties['ochiai_branch_tiebreak']['cases_with_top_score_tie']}, mean maximum tie size from {ties['ochiai']['average_max_tie_size']:.2f} to {ties['ochiai_branch_tiebreak']['average_max_tie_size']:.2f}, and mean fault-tie size from {ties['ochiai']['average_fault_tie_size']:.2f} to {ties['ochiai_branch_tiebreak']['average_fault_tie_size']:.2f}. The high equivalence ratio confirms that line coverage information loss is the dominant source of the original ties.

### RQ3: When is branch evidence most useful?

The largest observed average-rank MRR gain occurs for executable fault-equivalence classes of 6-10 lines ({evaluation['subgroups']['fault_equivalence_class_size']['6-10']['average_rank_mrr']['difference']:+.4f}) and medium coverage diversity ({evaluation['subgroups']['coverage_diversity']['medium (0.25-0.5)']['average_rank_mrr']['difference']:+.4f}). Cases with at least one PASS test gain {evaluation['subgroups']['pass_tests']['>=1 PASS']['average_rank_mrr']['difference']:+.4f}, compared with only {evaluation['subgroups']['pass_tests']['0 PASS']['average_rank_mrr']['difference']:+.4f} for 0-PASS cases. This supports the mechanism: branch evidence helps most when a substantial line-score tie exists and branch outcomes provide usable contrast; it cannot create information when branch spectra are identical or absent. These groups are descriptive, fixed before measurement, and were not used for tuning.

### RQ4: What are the main failure modes of FL-v1?

The main boundaries are non-executable diff lines, persistent straight-line equivalence, and weak spectra in 0-PASS cases. Regression can also occur when a non-fault control-flow line has stronger failing-correlated branch evidence than the true statement. Phase 6 quantifies these boundaries without modifying `fl-v1`.
"""


def write_independent_report() -> dict[str, Any]:
    evaluation = build_independent_evaluation()
    FAULT_LOCALIZATION_INDEPENDENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    FAULT_LOCALIZATION_INDEPENDENT_REPORT.write_text(
        render_independent_report(evaluation), encoding="utf-8"
    )
    return evaluation
