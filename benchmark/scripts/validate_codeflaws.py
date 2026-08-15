"""Validate Codeflaws manifest paths, sources, tests, and identifiers."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_MANIFEST,
    CODEFLAWS_VALIDATION_REPORT,
    PROJECT_ROOT,
)
from benchmark.models import BenchmarkCase, load_manifest  # noqa: E402


def _project_path(relative_path: str | None) -> Path | None:
    if relative_path is None or Path(relative_path).is_absolute():
        return None
    path = (PROJECT_ROOT / relative_path).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        return None
    return path


def validate_case(case: BenchmarkCase) -> tuple[bool, set[str]]:
    errors: set[str] = set()
    buggy = _project_path(case.buggy.source_path)
    reference = _project_path(case.reference.source_path)
    makefile = _project_path(case.metadata.get("makefile_path"))

    if buggy is None or not buggy.is_file():
        errors.add("missing_buggy")
    if reference is None or not reference.is_file():
        errors.add("missing_reference")
    if makefile is None or not makefile.is_file():
        errors.add("missing_makefile")

    for source in (buggy, reference):
        if source is not None and source.is_file():
            try:
                source.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeError):
                errors.add("unreadable_sources")

    if not case.tests.repair_tests or not case.tests.validation_tests:
        errors.add("missing_tests")
    for test in (*case.tests.repair_tests, *case.tests.validation_tests):
        input_path = _project_path(test.input_path)
        output_path = _project_path(test.expected_output_path)
        if (
            input_path is None
            or output_path is None
            or not input_path.is_file()
            or not output_path.is_file()
        ):
            errors.add("missing_tests")

    return not errors, errors


def validate_manifest(path: Path) -> dict[str, object]:
    cases = list(load_manifest(path))
    id_counts = Counter(case.case_id for case in cases)
    duplicate_ids = {case_id for case_id, count in id_counts.items() if count > 1}
    counts: Counter[str] = Counter()
    invalid_cases: list[dict[str, object]] = []

    for case in cases:
        valid, errors = validate_case(case)
        if case.case_id in duplicate_ids:
            errors.add("duplicate_ids")
            valid = False
        if valid:
            counts["valid"] += 1
        else:
            counts["invalid"] += 1
            invalid_cases.append(
                {"case_id": case.case_id, "reasons": sorted(errors)}
            )
        for error in errors:
            counts[error] += 1

    return {
        "total": len(cases),
        "valid": counts["valid"],
        "invalid": counts["invalid"],
        "missing_buggy": counts["missing_buggy"],
        "missing_reference": counts["missing_reference"],
        "missing_tests": counts["missing_tests"],
        "missing_makefile": counts["missing_makefile"],
        "unreadable_sources": counts["unreadable_sources"],
        "duplicate_ids": len(duplicate_ids),
        "invalid_cases": invalid_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=CODEFLAWS_MANIFEST)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    try:
        report = validate_manifest(args.manifest)
    except ValueError as exc:
        print(f"validate_codeflaws: {exc}", file=sys.stderr)
        return 1
    CODEFLAWS_VALIDATION_REPORT.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if args.strict and report["invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
