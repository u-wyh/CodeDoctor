"""Collect repair-test spectra and evaluate SBFL on the Codeflaws Pilot Set."""

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_PILOT,
    FAULT_LOCALIZATION_COVERAGE_ROOT,
    FAULT_LOCALIZATION_GROUND_TRUTH,
    FAULT_LOCALIZATION_RANKING_ROOT,
)
from benchmark.models import load_manifest  # noqa: E402
from fault_localization.collector import (  # noqa: E402
    CoverageCollectionError,
    collect_coverage,
)
from fault_localization.ground_truth import build_ground_truth  # noqa: E402
from fault_localization.models import LocalizationInput  # noqa: E402
from fault_localization.models import CoverageMatrix  # noqa: E402
from fault_localization.pipeline import localize  # noqa: E402


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
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--reuse-coverage",
        action="store_true",
        help="rebuild rankings from saved coverage without executing tests",
    )
    args = parser.parse_args()

    cases = list(load_manifest(CODEFLAWS_PILOT))
    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in cases}
        if missing:
            print(f"unknown Pilot case ids: {sorted(missing)}", file=sys.stderr)
            return 1
    if args.limit is not None:
        cases = cases[: args.limit]
    if args.force:
        for directory in (
            FAULT_LOCALIZATION_COVERAGE_ROOT,
            FAULT_LOCALIZATION_RANKING_ROOT,
        ):
            if directory.exists():
                shutil.rmtree(directory)

    ground_truth_records: list[dict[str, object]] = []
    errors = 0
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
        coverage_path = FAULT_LOCALIZATION_COVERAGE_ROOT / f"{case.case_id}.json"
        ranking_path = FAULT_LOCALIZATION_RANKING_ROOT / f"{case.case_id}.json"
        try:
            if args.reuse_coverage and coverage_path.exists():
                matrix = CoverageMatrix.from_dict(
                    json.loads(coverage_path.read_text(encoding="utf-8"))
                )
            else:
                repair_input = LocalizationInput.from_benchmark_case(case)
                matrix = collect_coverage(repair_input)
                coverage_document = matrix.to_dict()
                _write_json(coverage_path, coverage_document)
            ranking = localize(matrix, case.get_buggy_source())
            _write_json(ranking_path, ranking)
            print(
                f"  {ranking['status']}: {matrix.passed_tests} PASS, "
                f"{matrix.failed_tests} FAIL, "
                f"{len(matrix.executable_lines)} executable lines",
                flush=True,
            )
        except (CoverageCollectionError, OSError, ValueError) as exc:
            errors += 1
            _write_json(
                ranking_path,
                {
                    "case_id": case.case_id,
                    "status": "coverage_collection_error",
                    "reason": str(exc),
                    "rankings": {},
                    "spectrum": [],
                },
            )
            print(f"  coverage_collection_error: {exc}", flush=True)

        ground_truth_records.append(build_ground_truth(case).to_dict())
        _write_jsonl(FAULT_LOCALIZATION_GROUND_TRUTH, ground_truth_records)

    print(
        json.dumps(
            {"cases": len(cases), "coverage_errors": errors}, indent=2
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
