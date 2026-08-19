"""Build the independent 100-case Phase 8 Repair Evaluation Set."""

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_FL_EVALUATION,
    CODEFLAWS_MANIFEST,
    CODEFLAWS_PILOT,
    CODEFLAWS_REPAIR_PILOT,
    PHASE8_ATTRIBUTES,
    PHASE8_EVALUATION_EXCLUDED,
    PHASE8_EVALUATION_RESULTS,
    PHASE8_EVALUATION_SET,
    PHASE8_EVALUATION_SUMMARY,
    PHASE8_FL,
    PHASE8_RANDOM_SEED,
    PHASE8_TARGET_SIZE,
    PHASE8_TEST_PARTITION,
    REPAIR_RESULT_ROOT,
)
from benchmark.execution import verify_case  # noqa: E402
from benchmark.models import BenchmarkCase, load_manifest  # noqa: E402
from benchmark.repair_set import (  # noqa: E402
    repair_candidate_order,
    repair_eligibility_reason,
    repair_verification_record,
)
from benchmark.scripts.run_repair_pilot_fl import (  # noqa: E402
    _attribute_record,
    _fl_record,
)
from benchmark.scripts.validate_codeflaws import validate_case  # noqa: E402
from fault_localization.collector import collect_coverage  # noqa: E402
from fault_localization.method_freeze import validate_frozen_method  # noqa: E402
from fault_localization.models import LocalizationInput  # noqa: E402
from fault_localization.pipeline import localize  # noqa: E402
from repair_phase8.partition import (  # noqa: E402
    PARTITION_VERSION,
    canonical_hash,
    derive_partition,
    partitioned_case,
)


COVERAGE_ROOT = REPAIR_RESULT_ROOT.parent / "repair_phase8" / "coverage"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    outputs = (
        PHASE8_EVALUATION_SET,
        PHASE8_EVALUATION_RESULTS,
        PHASE8_EVALUATION_EXCLUDED,
        PHASE8_EVALUATION_SUMMARY,
        PHASE8_FL,
        PHASE8_ATTRIBUTES,
        PHASE8_TEST_PARTITION,
    )
    if any(path.exists() for path in outputs) and not args.force:
        parser.error("Phase 8 selection outputs already exist; use --force explicitly")
    if args.force:
        for path in outputs:
            path.unlink(missing_ok=True)
        shutil.rmtree(COVERAGE_ROOT, ignore_errors=True)
    validate_frozen_method()

    prior_sets = {
        "fl_pilot": {case.case_id for case in load_manifest(CODEFLAWS_PILOT)},
        "fl_evaluation": {
            case.case_id for case in load_manifest(CODEFLAWS_FL_EVALUATION)
        },
        "repair_pilot": {
            case.case_id for case in load_manifest(CODEFLAWS_REPAIR_PILOT)
        },
    }
    prior_ids = set().union(*prior_sets.values())
    excluded: list[dict[str, object]] = [
        {
            "case_id": case_id,
            "reason": "historical_dataset_overlap",
            "stage": "prior_set_exclusion",
        }
        for case_id in sorted(prior_ids)
    ]
    static_candidates = []
    for case in load_manifest(CODEFLAWS_MANIFEST):
        if case.case_id in prior_ids:
            continue
        accepted, reasons = validate_case(case)
        if not accepted:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "details": sorted(reasons),
                    "reason": "static_validation_failed",
                    "stage": "static_validation",
                }
            )
        elif len(case.tests.validation_tests) < 2:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "reason": "insufficient_validation_tests",
                    "stage": "static_validation",
                    "validation_test_count": len(case.tests.validation_tests),
                }
            )
        else:
            static_candidates.append(case)
    candidates = repair_candidate_order(
        static_candidates, prior_ids, PHASE8_RANDOM_SEED
    )
    selected: list[dict[str, object]] = []
    partitions = []
    results: list[dict[str, object]] = []
    fl_records = []
    attributes = []
    started = time.monotonic()
    for candidate_index, original in enumerate(candidates, start=1):
        if len(selected) >= PHASE8_TARGET_SIZE:
            break
        partition = derive_partition(original, PHASE8_RANDOM_SEED)
        case = partitioned_case(original, partition)
        print(f"[{candidate_index}] verifying {case.case_id}", flush=True)
        verification = verify_case(case)
        reason = repair_eligibility_reason(verification)
        result = repair_verification_record(
            verification,
            seed=PHASE8_RANDOM_SEED,
            candidate_index=candidate_index,
            eligibility_reason=reason,
        )
        if reason is None:
            try:
                matrix = collect_coverage(LocalizationInput.from_benchmark_case(case))
                ranking = localize(matrix, case.get_buggy_source())
            except (OSError, RuntimeError, ValueError) as exc:
                reason = "fl_pipeline_failed"
                result["eligibility_reason"] = reason
                result["fl_error"] = f"{type(exc).__name__}: {exc}"
            else:
                coverage_path = COVERAGE_ROOT / f"{case.case_id}.json"
                _write_json(coverage_path, matrix.to_dict())
                value = case.to_dict()
                value["metadata"]["phase8"]["selection"] = {
                    "candidate_index": candidate_index,
                    "docker_verified": True,
                    "seed": PHASE8_RANDOM_SEED,
                }
                selected.append(value)
                partitions.append(partition)
                fl_records.append(_fl_record(case, ranking))
                attributes.append(_attribute_record(case, matrix, ranking))
                print(f"  included ({len(selected)}/{PHASE8_TARGET_SIZE})", flush=True)
        if reason is not None:
            excluded.append(
                {
                    "candidate_index": candidate_index,
                    "case_id": case.case_id,
                    "reason": reason,
                    "stage": "dynamic_verification",
                }
            )
            print(f"  excluded: {reason}", flush=True)
        results.append(result)
        _write_jsonl(PHASE8_EVALUATION_SET, selected)
        _write_jsonl(PHASE8_EVALUATION_RESULTS, results)
        _write_jsonl(PHASE8_EVALUATION_EXCLUDED, excluded)
        _write_jsonl(PHASE8_FL, fl_records)
        _write_jsonl(PHASE8_ATTRIBUTES, attributes)

    partition_value: dict[str, object] = {
        "case_count": len(partitions),
        "partitions": [item.to_dict() for item in partitions],
        "protocol_version": PARTITION_VERSION,
        "seed": PHASE8_RANDOM_SEED,
    }
    partition_value["overall_manifest_hash"] = canonical_hash(partition_value)
    _write_json(PHASE8_TEST_PARTITION, partition_value)
    selected_ids = {item["case_id"] for item in selected}
    reason_counts = Counter(str(item["reason"]) for item in excluded)
    summary = {
        "candidate_count": len(candidates),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exclusion_reasons": dict(sorted(reason_counts.items())),
        "exclusions": len(excluded),
        "fl_evaluation_overlap": len(selected_ids & prior_sets["fl_evaluation"]),
        "fl_performance_filtering": False,
        "fl_pilot_overlap": len(selected_ids & prior_sets["fl_pilot"]),
        "repair_pilot_overlap": len(selected_ids & prior_sets["repair_pilot"]),
        "seed": PHASE8_RANDOM_SEED,
        "selected_cases": len(selected),
        "selection_inputs": [
            "static benchmark validity and complete artifacts",
            "at least two validation tests before deterministic partitioning",
            "reference compile and all partitioned tests pass",
            "buggy compile and at least one public repair-time test fails",
            "runner and frozen FL-v1 pipeline complete",
            "zero overlap with all prior formal sets",
        ],
        "target_size": PHASE8_TARGET_SIZE,
        "test_partition_manifest_hash": partition_value["overall_manifest_hash"],
    }
    _write_json(PHASE8_EVALUATION_SUMMARY, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if len(selected) == PHASE8_TARGET_SIZE else 1


if __name__ == "__main__":
    raise SystemExit(main())
