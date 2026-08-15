"""Export a small, self-contained schema sample from the verified pilot."""

import json
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_PILOT,
    CODEFLAWS_SAMPLE_ROOT,
    PROJECT_ROOT,
)
from benchmark.models import BenchmarkCase, BenchmarkTest, load_manifest  # noqa: E402


def _copy(path_value: str, destination: Path) -> str:
    source = PROJECT_ROOT / path_value
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination.relative_to(PROJECT_ROOT).as_posix()


def _sample_test(
    test: BenchmarkTest, destination: Path, suite: str
) -> BenchmarkTest:
    input_path = _copy(
        str(test.input_path), destination / f"{suite}-{test.test_id}.in"
    )
    output_path = _copy(
        str(test.expected_output_path), destination / f"{suite}-{test.test_id}.out"
    )
    return BenchmarkTest(test.test_id, input_path, output_path)


def main() -> int:
    cases = list(load_manifest(CODEFLAWS_PILOT))[:3]
    if not cases:
        print("pilot manifest is empty", file=sys.stderr)
        return 1
    if CODEFLAWS_SAMPLE_ROOT.exists():
        shutil.rmtree(CODEFLAWS_SAMPLE_ROOT)
    CODEFLAWS_SAMPLE_ROOT.mkdir(parents=True)
    records: list[dict[str, object]] = []
    for case in cases:
        destination = CODEFLAWS_SAMPLE_ROOT / case.case_id
        buggy_path = _copy(case.buggy.source_path, destination / "buggy.c")
        reference_path = _copy(case.reference.source_path, destination / "reference.c")
        makefile_path = _copy(
            str(case.metadata["makefile_path"]), destination / "Makefile"
        )
        repair = _sample_test(case.tests.repair_tests[0], destination, "repair")
        validation = _sample_test(
            case.tests.validation_tests[0], destination, "validation"
        )
        value = case.to_dict()
        value["buggy"]["source_path"] = buggy_path
        value["reference"]["source_path"] = reference_path
        value["tests"] = {
            "repair_tests": [repair.__dict__],
            "validation_tests": [validation.__dict__],
        }
        value["metadata"] = {
            "defect_class": case.metadata["defect_class"],
            "makefile_path": makefile_path,
            "original_case_id": case.case_id,
            "sample_only": True,
            "reference_usage": "evaluation_only",
        }
        records.append(value)
    manifest = CODEFLAWS_SAMPLE_ROOT / "sample_manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )
    (CODEFLAWS_SAMPLE_ROOT / "README.md").write_text(
        "# Codeflaws Sample\n\n"
        "This tracked sample contains three verified pilot cases with one repair "
        "and one validation test each. It demonstrates the schema only and is not "
        "the complete evaluation set. Reference sources are evaluation-only.\n",
        encoding="utf-8",
    )
    print(json.dumps({"sample_cases": len(records), "manifest": str(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
