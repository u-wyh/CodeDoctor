"""Build a stratified, Docker-verified Codeflaws pilot manifest."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_EXCLUDED,
    CODEFLAWS_MANIFEST,
    CODEFLAWS_PILOT,
    CODEFLAWS_PILOT_RESULTS,
    PILOT_RANDOM_SEED,
    PILOT_TARGET_SIZE,
)
from benchmark.execution import verify_case  # noqa: E402
from benchmark.models import BenchmarkCase, load_manifest  # noqa: E402
from benchmark.sampling import stratified_case_order  # noqa: E402
from benchmark.scripts.validate_codeflaws import validate_case  # noqa: E402


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, sort_keys=True) + "\n")
    temporary.replace(path)


def _pilot_record(case: BenchmarkCase, verification: dict[str, object], seed: int) -> dict[str, object]:
    value = case.to_dict()
    value["metadata"]["pilot"] = {
        "seed": seed,
        "docker_verified": True,
        "verification_result": verification,
    }
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-size", type=int, default=PILOT_TARGET_SIZE)
    parser.add_argument("--seed", type=int, default=PILOT_RANDOM_SEED)
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.target_size <= 0:
        parser.error("--target-size must be positive")
    outputs = (CODEFLAWS_PILOT, CODEFLAWS_EXCLUDED, CODEFLAWS_PILOT_RESULTS)
    if not args.force and any(path.exists() for path in outputs):
        print("pilot outputs already exist; pass --force to rebuild", file=sys.stderr)
        return 1

    all_cases = list(load_manifest(CODEFLAWS_MANIFEST))
    valid_cases: list[BenchmarkCase] = []
    excluded: list[dict[str, object]] = []
    for case in all_cases:
        valid, reasons = validate_case(case)
        if valid:
            valid_cases.append(case)
        else:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "stage": "static_validation",
                    "reason": "static_validation_failed",
                    "details": sorted(reasons),
                }
            )

    candidates = stratified_case_order(valid_cases, args.seed)
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    pilot: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    for index, case in enumerate(candidates, start=1):
        if len(pilot) >= args.target_size:
            break
        print(
            f"[{index}] verifying {case.case_id} "
            f"({case.metadata.get('defect_class')})",
            flush=True,
        )
        verification = verify_case(case)
        record = verification.to_dict()
        record["candidate_index"] = index
        record["seed"] = args.seed
        results.append(record)
        if verification.reproducible:
            pilot.append(_pilot_record(case, record, args.seed))
            print(f"  included ({len(pilot)}/{args.target_size})", flush=True)
        else:
            excluded.append(
                {
                    "case_id": case.case_id,
                    "stage": "dynamic_verification",
                    "reason": verification.exclusion_reason,
                    "details": record,
                }
            )
            print(f"  excluded: {verification.exclusion_reason}", flush=True)

        _write_jsonl(CODEFLAWS_PILOT, pilot)
        _write_jsonl(CODEFLAWS_EXCLUDED, excluded)
        _write_jsonl(CODEFLAWS_PILOT_RESULTS, results)

    summary = {
        "seed": args.seed,
        "target_size": args.target_size,
        "pilot_size": len(pilot),
        "dynamic_candidates_tested": len(results),
        "excluded_total": len(excluded),
    }
    print(json.dumps(summary, indent=2))
    return 0 if len(pilot) == args.target_size else 1


if __name__ == "__main__":
    raise SystemExit(main())
