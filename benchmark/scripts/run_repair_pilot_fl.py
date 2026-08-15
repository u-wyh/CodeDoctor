"""Collect frozen FL-v1 evidence and evaluation-only attributes for Repair Pilot."""

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    REPAIR_PILOT_ATTRIBUTES,
    REPAIR_PILOT_FL,
    REPAIR_RESULT_ROOT,
)
from benchmark.models import load_manifest  # noqa: E402
from fault_localization.collector import collect_coverage  # noqa: E402
from fault_localization.evaluation import evaluate_case  # noqa: E402
from fault_localization.ground_truth import build_ground_truth  # noqa: E402
from fault_localization.independent_evaluation import (  # noqa: E402
    has_straight_line_ambiguity,
    is_non_executable_fault,
)
from fault_localization.method_freeze import validate_frozen_method  # noqa: E402
from fault_localization.models import CoverageMatrix, LocalizationInput, RankedLine  # noqa: E402
from fault_localization.pipeline import localize  # noqa: E402
from fault_localization.tie_analysis import coverage_equivalence_classes  # noqa: E402


COVERAGE_ROOT = REPAIR_RESULT_ROOT / "coverage"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in values),
        encoding="utf-8",
    )
    temporary.replace(path)


def _fl_record(case: object, ranking: dict[str, object]) -> dict[str, object]:
    entries = ranking["rankings"]["ochiai_branch_tiebreak"][:10]
    reliable = bool(entries) and max(float(item["score"]) for item in entries) > 0.0
    return {
        "availability_message": (
            "Frozen FL-v1 Top-10 locations are available."
            if reliable
            else "No reliable suspicious location is available from FL-v1."
        ),
        "case_id": case.case_id,
        "method_version": "fl-v1",
        "reliable_locations_available": reliable,
        "top_k": 10,
        "locations": [
            {
                "branch_score": item["branch_score"],
                "line": item["line"],
                "line_score": item["score"],
                "rank": item["rank"],
                "source_line": item["source_snippet"],
                "tie_end_rank": item["tie_end_rank"],
                "tie_start_rank": item["tie_start_rank"],
            }
            for item in entries if reliable
        ],
    }


def _attribute_record(
    case: object, matrix: CoverageMatrix, ranking: dict[str, object]
) -> dict[str, object]:
    faults = build_ground_truth(case).fault_lines
    ranked = tuple(
        RankedLine(**item)
        for item in ranking["rankings"]["ochiai_branch_tiebreak"]
    )
    metric = evaluate_case(ranked, faults)
    vectors = {
        line: tuple(int(line in test.covered_lines) for test in matrix.tests)
        for line in matrix.executable_lines
    }
    classes = coverage_equivalence_classes(matrix)
    class_by_line = {
        line: len(group.lines) for group in classes for line in group.lines
    }
    executable_fault_sizes = [class_by_line[line] for line in faults if line in class_by_line]
    first_rank = metric.first_fault_rank
    return {
        "case_id": case.case_id,
        "coverage_diversity_ratio": len(classes) / len(matrix.executable_lines),
        "fault_equivalence_class_size": (
            max(executable_fault_sizes) if executable_fault_sizes else None
        ),
        "fault_lines": list(faults),
        "fl_first_fault_rank": first_rank,
        "fl_top_1_hit": first_rank is not None and first_rank <= 1,
        "fl_top_5_hit": first_rank is not None and first_rank <= 5,
        "fl_top_10_hit": first_rank is not None and first_rank <= 10,
        "non_executable_fault": is_non_executable_fault(
            faults, set(matrix.executable_lines)
        ),
        "passed_repair_tests": matrix.passed_tests,
        "straight_line_ambiguity": has_straight_line_ambiguity(
            faults, ranked, vectors
        ),
        "zero_pass": matrix.passed_tests == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reuse-coverage", action="store_true")
    args = parser.parse_args()
    validate_frozen_method()
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    if args.limit is not None:
        cases = cases[: args.limit]
    if args.force:
        shutil.rmtree(COVERAGE_ROOT, ignore_errors=True)
        REPAIR_PILOT_FL.unlink(missing_ok=True)
        REPAIR_PILOT_ATTRIBUTES.unlink(missing_ok=True)

    fl_records = []
    attribute_records = []
    errors = 0
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
        coverage_path = COVERAGE_ROOT / f"{case.case_id}.json"
        try:
            if args.reuse_coverage and coverage_path.exists():
                matrix = CoverageMatrix.from_dict(
                    json.loads(coverage_path.read_text(encoding="utf-8"))
                )
            else:
                matrix = collect_coverage(LocalizationInput.from_benchmark_case(case))
                _write_json(coverage_path, matrix.to_dict())
            ranking = localize(matrix, case.get_buggy_source())
            fl_records.append(_fl_record(case, ranking))
            attribute_records.append(_attribute_record(case, matrix, ranking))
            print(
                f"  {matrix.passed_tests} PASS, {matrix.failed_tests} FAIL, "
                f"{len(matrix.executable_lines)} lines",
                flush=True,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors += 1
            print(f"  error: {exc}", file=sys.stderr, flush=True)
        _write_jsonl(REPAIR_PILOT_FL, fl_records)
        _write_jsonl(REPAIR_PILOT_ATTRIBUTES, attribute_records)
    print(json.dumps({"cases": len(cases), "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
