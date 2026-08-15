"""Codeflaws raw-layout discovery and conversion to BenchmarkCase."""

import re
from pathlib import Path
from typing import Any, Iterable

from .config import CODEFLAWS_RAW_ROOT, PROJECT_ROOT
from .models import (
    BenchmarkCase,
    BenchmarkTest,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)


CASE_NAME = re.compile(
    r"^(?P<contest>[^-]+)-(?P<problem>.+)-bug-"
    r"(?P<buggy_submission>\d+)-(?P<reference_submission>\d+)$"
)
REPAIR_INPUT = re.compile(r"^input-?(?P<id>.+)$")
REPAIR_OUTPUT = re.compile(r"^output-?(?P<id>.+)$")
VALIDATION_INPUT = re.compile(r"^heldout-input-?(?P<id>.+)$")
VALIDATION_OUTPUT = re.compile(r"^heldout-output-?(?P<id>.+)$")
SCRIPT_TEST = re.compile(
    r'^\s*(?P<label>[^)]+)\)\s+run_test\s+'
    r'"\$(?P<input_var>INPUT_NAME|NEGINPUT_NAME)"(?P<input_index>\d+)\s+'
    r'"\$(?P<output_var>OUTPUT_NAME|NEGOUTPUT_NAME)"(?P<output_index>\d+)\s*;;'
)


def find_benchmark_root(raw_root: Path = CODEFLAWS_RAW_ROOT) -> Path:
    search_roots = [raw_root, *(path for path in raw_root.iterdir() if path.is_dir())]
    candidates = [
        path
        for path in search_roots
        if any(CASE_NAME.match(child.name) for child in path.iterdir())
    ]
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"expected one Codeflaws benchmark directory under {raw_root}, "
            f"found {len(candidates)}"
        )
    return candidates[0]


def discover_case_directories(benchmark_root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in benchmark_root.iterdir()
            if path.is_dir() and CASE_NAME.match(path.name)
        ),
        key=lambda path: path.name,
    )


def parse_case_directory(
    case_directory: Path,
    classifications: dict[str, dict[str, str]],
) -> BenchmarkCase:
    match = CASE_NAME.match(case_directory.name)
    if match is None:
        raise ValueError(f"invalid Codeflaws case directory: {case_directory.name}")

    values = match.groupdict()
    source_prefix = f"{values['contest']}-{values['problem']}"
    buggy_source = case_directory / (
        f"{source_prefix}-{values['buggy_submission']}.c"
    )
    reference_source = case_directory / (
        f"{source_prefix}-{values['reference_submission']}.c"
    )
    classification = classifications.get(case_directory.name, {})

    return BenchmarkCase(
        case_id=case_directory.name,
        dataset="codeflaws",
        language="c",
        problem=ProblemIdentity(
            contest_id=values["contest"],
            problem_id=values["problem"],
        ),
        buggy=ProgramArtifact(
            source_path=_relative(buggy_source),
            submission_id=values["buggy_submission"],
        ),
        reference=ProgramArtifact(
            source_path=_relative(reference_source),
            submission_id=values["reference_submission"],
        ),
        tests=TestSuites(
            repair_tests=tuple(
                _discover_script_tests(
                    case_directory,
                    case_directory / "test-genprog.sh",
                    repair=True,
                )
            ),
            validation_tests=tuple(
                _discover_script_tests(
                    case_directory,
                    case_directory / "test-valid.sh",
                    repair=False,
                )
            ),
        ),
        metadata={
            "defect_class": classification.get("defect_class", "unknown"),
            "error_type": classification.get("error_type"),
            "error_code": classification.get("error_code"),
            "original_dataset_path": _relative(case_directory),
            "makefile_path": _relative(case_directory / "Makefile"),
            "repair_test_script_path": _relative(
                case_directory / "test-genprog.sh"
            ),
            "validation_test_script_path": _relative(
                case_directory / "test-valid.sh"
            ),
            "reference_usage": "evaluation_only",
        },
    )


def _discover_script_tests(
    directory: Path, script_path: Path, *, repair: bool
) -> Iterable[BenchmarkTest]:
    if script_path.is_file():
        script = script_path.read_text(encoding="utf-8", errors="replace")
        mappings = []
        for line in script.splitlines():
            match = SCRIPT_TEST.match(line)
            if match is None:
                continue
            values = match.groupdict()
            input_prefix = (
                "input-neg" if values["input_var"] == "NEGINPUT_NAME" else "input-pos"
            )
            output_prefix = (
                "output-neg"
                if values["output_var"] == "NEGOUTPUT_NAME"
                else "output-pos"
            )
            if not repair:
                input_prefix = "heldout-" + input_prefix
                output_prefix = "heldout-" + output_prefix
            mappings.append(
                BenchmarkTest(
                    test_id=values["label"].strip(),
                    input_path=_relative(
                        directory / f"{input_prefix}{values['input_index']}"
                    ),
                    expected_output_path=_relative(
                        directory / f"{output_prefix}{values['output_index']}"
                    ),
                )
            )
        if mappings:
            yield from mappings
            return

    input_pattern = REPAIR_INPUT if repair else VALIDATION_INPUT
    output_pattern = REPAIR_OUTPUT if repair else VALIDATION_OUTPUT
    yield from _discover_tests(directory, input_pattern, output_pattern)


def _discover_tests(
    directory: Path,
    input_pattern: re.Pattern[str],
    output_pattern: re.Pattern[str],
) -> Iterable[BenchmarkTest]:
    inputs = _indexed_paths(directory, input_pattern)
    outputs = _indexed_paths(directory, output_pattern)
    for test_id in sorted(set(inputs) | set(outputs), key=_natural_key):
        yield BenchmarkTest(
            test_id=test_id,
            input_path=_relative(inputs[test_id]) if test_id in inputs else None,
            expected_output_path=(
                _relative(outputs[test_id]) if test_id in outputs else None
            ),
        )


def _indexed_paths(
    directory: Path, pattern: re.Pattern[str]
) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in directory.iterdir():
        match = pattern.match(path.name)
        if path.is_file() and match is not None:
            indexed[match.group("id")] = path
    return indexed


def _relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def _natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value)
    )
