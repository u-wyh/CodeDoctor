"""Build a disjoint, stratified, Docker-verified Repair Pilot Set."""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_FL_EVALUATION,
    CODEFLAWS_MANIFEST,
    CODEFLAWS_PILOT,
    CODEFLAWS_REPAIR_PILOT,
    CODEFLAWS_REPAIR_PILOT_EXCLUDED,
    CODEFLAWS_REPAIR_PILOT_RESULTS,
    CODEFLAWS_REPAIR_PILOT_SUMMARY,
    REPAIR_PILOT_RANDOM_SEED,
    REPAIR_PILOT_TARGET_SIZE,
)
from benchmark.execution import verify_case  # noqa: E402
from benchmark.models import BenchmarkCase, load_manifest  # noqa: E402
from benchmark.repair_set import (  # noqa: E402
    repair_candidate_order,
    repair_eligibility_reason,
    repair_record,
    repair_verification_record,
)
from benchmark.scripts.validate_codeflaws import validate_case  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _static_candidates(
    all_cases: list[BenchmarkCase], excluded_ids: set[str]
) -> tuple[list[BenchmarkCase], list[dict[str, object]]]:
    valid = []
    excluded = []
    for case in all_cases:
        if case.case_id in excluded_ids:
            continue
        accepted, reasons = validate_case(case)
        if accepted:
            valid.append(case)
        else:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "reason": "static_validation_failed",
                    "stage": "static_validation",
                    "details": sorted(reasons),
                }
            )
    return valid, excluded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, default=REPAIR_PILOT_TARGET_SIZE)
    parser.add_argument("--seed", type=int, default=REPAIR_PILOT_RANDOM_SEED)
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.target_size <= 0:
        parser.error("--target-size must be positive")

    outputs = (
        CODEFLAWS_REPAIR_PILOT,
        CODEFLAWS_REPAIR_PILOT_EXCLUDED,
        CODEFLAWS_REPAIR_PILOT_RESULTS,
        CODEFLAWS_REPAIR_PILOT_SUMMARY,
    )
    if args.force:
        for path in outputs:
            path.unlink(missing_ok=True)

    pilot_ids = {case.case_id for case in load_manifest(CODEFLAWS_PILOT)}
    evaluation_ids = {
        case.case_id for case in load_manifest(CODEFLAWS_FL_EVALUATION)
    }
    prior_ids = pilot_ids | evaluation_ids
    all_cases = list(load_manifest(CODEFLAWS_MANIFEST))
    valid, static_excluded = _static_candidates(all_cases, prior_ids)
    candidates = repair_candidate_order(valid, prior_ids, args.seed)
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]

    selected = _read_jsonl(CODEFLAWS_REPAIR_PILOT)
    results = _read_jsonl(CODEFLAWS_REPAIR_PILOT_RESULTS)
    excluded = _read_jsonl(CODEFLAWS_REPAIR_PILOT_EXCLUDED)
    if not excluded:
        excluded = list(static_excluded)
    tested_ids = {str(record["case_id"]) for record in results}
    selected_ids = {str(record["case_id"]) for record in selected}
    if selected_ids & prior_ids:
        print("existing Repair Pilot overlaps a frozen prior set", file=sys.stderr)
        return 1
    if any(int(record.get("seed", args.seed)) != args.seed for record in results):
        print("existing results use a different seed; pass --force", file=sys.stderr)
        return 1

    started = time.monotonic()
    for candidate_index, case in enumerate(candidates, start=1):
        if len(selected) >= args.target_size:
            break
        if case.case_id in tested_ids:
            continue
        print(f"[{candidate_index}] verifying {case.case_id}", flush=True)
        verification = verify_case(case)
        reason = repair_eligibility_reason(verification)
        results.append(
            repair_verification_record(
                verification,
                seed=args.seed,
                candidate_index=candidate_index,
                eligibility_reason=reason,
            )
        )
        tested_ids.add(case.case_id)
        if reason is None:
            selected.append(
                repair_record(
                    case,
                    verification,
                    seed=args.seed,
                    candidate_index=candidate_index,
                )
            )
            selected_ids.add(case.case_id)
            print(f"  included ({len(selected)}/{args.target_size})", flush=True)
        else:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "reason": reason,
                    "stage": "dynamic_verification",
                    "candidate_index": candidate_index,
                }
            )
            print(f"  excluded: {reason}", flush=True)
        _write_jsonl(CODEFLAWS_REPAIR_PILOT, selected)
        _write_jsonl(CODEFLAWS_REPAIR_PILOT_RESULTS, results)
        _write_jsonl(CODEFLAWS_REPAIR_PILOT_EXCLUDED, excluded)

    elapsed = time.monotonic() - started
    dynamic_reasons = Counter(
        str(item["reason"])
        for item in excluded
        if item.get("stage") == "dynamic_verification"
    )
    summary: dict[str, object] = {
        "candidate_count": len(candidates),
        "defect_class_distribution": dict(
            sorted(
                Counter(
                    str(item["metadata"].get("defect_class") or "unknown")
                    for item in selected
                ).items()
            )
        ),
        "dynamic_candidates_tested": len(results),
        "dynamic_exclusion_reasons": dict(sorted(dynamic_reasons.items())),
        "dynamic_exclusions": sum(dynamic_reasons.values()),
        "elapsed_seconds_this_run": round(elapsed, 3),
        "fl_evaluation_overlap": len(selected_ids & evaluation_ids),
        "fl_performance_filtering": False,
        "fl_pilot_overlap": len(selected_ids & pilot_ids),
        "repair_pilot_size": len(selected),
        "seed": args.seed,
        "selection_inputs": [
            "static benchmark validity",
            "reference compile and repair/validation success",
            "buggy compile and at least one failing repair test",
            "disjointness from FL Pilot and FL Evaluation",
        ],
        "static_exclusions": len(static_excluded),
        "target_size": args.target_size,
    }
    _write_json(CODEFLAWS_REPAIR_PILOT_SUMMARY, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if len(selected) == args.target_size else 1


if __name__ == "__main__":
    raise SystemExit(main())
