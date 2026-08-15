"""Compute and render the Codeflaws pilot report from generated artifacts."""

import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import (
    CODEFLAWS_EXCLUDED,
    CODEFLAWS_PILOT,
    CODEFLAWS_PILOT_REPORT,
    CODEFLAWS_PILOT_REPORT_DATA,
    CODEFLAWS_PILOT_RESULTS,
    CODEFLAWS_VALIDATION_REPORT,
)
from .models import BenchmarkCase, load_manifest


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _distribution(values: Iterable[int]) -> dict[str, float | int]:
    items = list(values)
    if not items:
        return {"min": 0, "median": 0, "mean": 0, "max": 0}
    return {
        "min": min(items),
        "median": statistics.median(items),
        "mean": round(statistics.fmean(items), 2),
        "max": max(items),
    }


def build_report_data() -> dict[str, object]:
    validation = json.loads(CODEFLAWS_VALIDATION_REPORT.read_text(encoding="utf-8"))
    pilot_cases = list(load_manifest(CODEFLAWS_PILOT))
    results = _load_jsonl(CODEFLAWS_PILOT_RESULTS)
    excluded = _load_jsonl(CODEFLAWS_EXCLUDED)
    class_counts = Counter(
        str(case.metadata.get("defect_class") or "unknown") for case in pilot_cases
    )
    exclusion_counts = Counter(str(item["reason"]) for item in excluded)
    dynamic_count = len(results)
    buggy_compiles = sum(bool(item["buggy_compile"]["success"]) for item in results)
    reference_compiles = sum(
        bool(item["reference_compile"]["success"]) for item in results
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_manifest_cases": validation["total"],
        "statically_valid_cases": validation["valid"],
        "statically_invalid_cases": validation["invalid"],
        "pilot_size": len(pilot_cases),
        "pilot_defect_classes": dict(sorted(class_counts.items())),
        "repair_test_count": _distribution(
            len(case.tests.repair_tests) for case in pilot_cases
        ),
        "validation_test_count": _distribution(
            len(case.tests.validation_tests) for case in pilot_cases
        ),
        "total_test_count": _distribution(
            len(case.tests.repair_tests) + len(case.tests.validation_tests)
            for case in pilot_cases
        ),
        "dynamic_candidates_tested": dynamic_count,
        "buggy_compile_success": buggy_compiles,
        "buggy_compile_success_rate": (
            round(buggy_compiles / dynamic_count, 4) if dynamic_count else 0
        ),
        "reference_compile_success": reference_compiles,
        "reference_compile_success_rate": (
            round(reference_compiles / dynamic_count, 4) if dynamic_count else 0
        ),
        "reproducible_cases": sum(bool(item["reproducible"]) for item in results),
        "reproducible_rate": (
            round(
                sum(bool(item["reproducible"]) for item in results) / dynamic_count,
                4,
            )
            if dynamic_count
            else 0
        ),
        "excluded_total": len(excluded),
        "excluded_by_reason": dict(sorted(exclusion_counts.items())),
    }


def render_report(data: dict[str, object]) -> str:
    classes = "\n".join(
        f"| {name} | {count} |"
        for name, count in data["pilot_defect_classes"].items()
    )
    reasons = "\n".join(
        f"| {name} | {count} |"
        for name, count in data["excluded_by_reason"].items()
    )
    repair = data["repair_test_count"]
    validation = data["validation_test_count"]
    total = data["total_test_count"]
    return f"""# Codeflaws Pilot Report

Generated from the current manifest and Docker verification artifacts at `{data['generated_at']}`.

## Dataset Summary

| Metric | Value |
| --- | ---: |
| Parsed cases | {data['raw_manifest_cases']} |
| Statically valid cases | {data['statically_valid_cases']} |
| Statically invalid cases | {data['statically_invalid_cases']} |
| Dynamic candidates tested | {data['dynamic_candidates_tested']} |
| Pilot cases | {data['pilot_size']} |
| Excluded records | {data['excluded_total']} |

## Reproduction Results

| Metric | Result |
| --- | ---: |
| Buggy compile success | {data['buggy_compile_success']} / {data['dynamic_candidates_tested']} ({data['buggy_compile_success_rate']:.2%}) |
| Reference compile success | {data['reference_compile_success']} / {data['dynamic_candidates_tested']} ({data['reference_compile_success_rate']:.2%}) |
| Reproducible cases | {data['reproducible_cases']} / {data['dynamic_candidates_tested']} ({data['reproducible_rate']:.2%}) |

A case is reproducible only when both programs compile, the reference passes every repair and validation test, and the buggy program fails at least one test.

## Test Counts Per Pilot Case

| Suite | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: |
| Repair | {repair['min']} | {repair['median']} | {repair['mean']} | {repair['max']} |
| Validation | {validation['min']} | {validation['median']} | {validation['mean']} | {validation['max']} |
| Total | {total['min']} | {total['median']} | {total['mean']} | {total['max']} |

## Defect Class Distribution

| Defect class | Cases |
| --- | ---: |
{classes}

## Exclusion Reasons

| Reason | Cases |
| --- | ---: |
{reasons}
"""


def write_report() -> dict[str, object]:
    data = build_report_data()
    CODEFLAWS_PILOT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    CODEFLAWS_PILOT_REPORT.write_text(render_report(data), encoding="utf-8")
    CODEFLAWS_PILOT_REPORT_DATA.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data
