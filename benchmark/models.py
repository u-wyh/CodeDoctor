"""Unified benchmark case model independent of Codeflaws layout."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

from .config import CODEFLAWS_MANIFEST, PROJECT_ROOT


@dataclass(frozen=True)
class BenchmarkTest:
    test_id: str
    input_path: str | None
    expected_output_path: str | None


@dataclass(frozen=True)
class ProgramArtifact:
    source_path: str
    submission_id: str


@dataclass(frozen=True)
class ProblemIdentity:
    contest_id: str
    problem_id: str


@dataclass(frozen=True)
class TestSuites:
    repair_tests: tuple[BenchmarkTest, ...]
    validation_tests: tuple[BenchmarkTest, ...]


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    dataset: str
    language: str
    problem: ProblemIdentity
    buggy: ProgramArtifact
    reference: ProgramArtifact
    tests: TestSuites
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BenchmarkCase":
        tests = value["tests"]
        return cls(
            case_id=value["case_id"],
            dataset=value["dataset"],
            language=value["language"],
            problem=ProblemIdentity(**value["problem"]),
            buggy=ProgramArtifact(**value["buggy"]),
            reference=ProgramArtifact(**value["reference"]),
            tests=TestSuites(
                repair_tests=tuple(
                    BenchmarkTest(**item) for item in tests["repair_tests"]
                ),
                validation_tests=tuple(
                    BenchmarkTest(**item) for item in tests["validation_tests"]
                ),
            ),
            metadata=value["metadata"],
        )

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self)))

    def get_buggy_source(self, project_root: Path = PROJECT_ROOT) -> str:
        return _read_project_file(self.buggy.source_path, project_root)

    def get_reference_source(
        self,
        *,
        evaluation_only: bool = False,
        project_root: Path = PROJECT_ROOT,
    ) -> str:
        if not evaluation_only:
            raise PermissionError(
                "reference source is evaluation-only; pass evaluation_only=True explicitly"
            )
        return _read_project_file(self.reference.source_path, project_root)

    def get_repair_tests(self) -> tuple[BenchmarkTest, ...]:
        return self.tests.repair_tests

    def get_validation_tests(self) -> tuple[BenchmarkTest, ...]:
        return self.tests.validation_tests

    def repair_time_view(self) -> dict[str, Any]:
        """Return case information safe to expose to a future repair system."""

        return {
            "case_id": self.case_id,
            "dataset": self.dataset,
            "language": self.language,
            "problem": asdict(self.problem),
            "buggy": asdict(self.buggy),
            "tests": {
                "repair_tests": [asdict(item) for item in self.tests.repair_tests]
            },
            "metadata": {
                "defect_class": self.metadata.get("defect_class"),
                "original_dataset_path": self.metadata.get(
                    "original_dataset_path"
                ),
            },
        }


def _read_project_file(relative_path: str, project_root: Path) -> str:
    path = (project_root / relative_path).resolve()
    root = project_root.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"benchmark path escapes project root: {relative_path}")
    return path.read_text(encoding="utf-8", errors="replace")


def load_manifest(path: Path = CODEFLAWS_MANIFEST) -> Iterator[BenchmarkCase]:
    with path.open(encoding="utf-8") as manifest:
        for line_number, line in enumerate(manifest, start=1):
            if not line.strip():
                continue
            try:
                yield BenchmarkCase.from_dict(json.loads(line))
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid manifest entry at {path}:{line_number}: {exc}"
                ) from exc


def load_case(case_id: str, path: Path = CODEFLAWS_MANIFEST) -> BenchmarkCase:
    for case in load_manifest(path):
        if case.case_id == case_id:
            return case
    raise KeyError(f"benchmark case not found: {case_id}")
