"""Data models shared by coverage, spectrum, ranking, and evaluation."""

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from benchmark.models import BenchmarkCase, BenchmarkTest


class TestVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class LocalizationInput:
    """Repair-time-only view; intentionally has no reference or validation data."""

    case_id: str
    buggy_source_path: str
    repair_tests: tuple[BenchmarkTest, ...]
    metadata: dict[str, Any]

    @classmethod
    def from_benchmark_case(cls, case: BenchmarkCase) -> "LocalizationInput":
        view = case.repair_time_view()
        return cls(
            case_id=view["case_id"],
            buggy_source_path=view["buggy"]["source_path"],
            repair_tests=tuple(
                BenchmarkTest(**item)
                for item in view["tests"]["repair_tests"]
            ),
            metadata=view["metadata"],
        )


@dataclass(frozen=True)
class BranchCoverage:
    line: int
    branch_index: int
    count: int
    taken: bool
    fallthrough: bool
    throw: bool


@dataclass(frozen=True)
class TestCoverage:
    test_id: str
    verdict: TestVerdict
    covered_lines: tuple[int, ...]
    executable_lines: tuple[int, ...]
    exit_code: int | None
    timed_out: bool
    gcov_version: str
    branches: tuple[BranchCoverage, ...] = ()


@dataclass(frozen=True)
class CoverageMatrix:
    case_id: str
    source_path: str
    compile_command: tuple[str, ...]
    compile_stdout: str
    compile_stderr: str
    tests: tuple[TestCoverage, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CoverageMatrix":
        return cls(
            case_id=value["case_id"],
            source_path=value["source_path"],
            compile_command=tuple(value["compile_command"]),
            compile_stdout=value["compile_stdout"],
            compile_stderr=value["compile_stderr"],
            tests=tuple(
                TestCoverage(
                    test_id=item["test_id"],
                    verdict=TestVerdict(item["verdict"]),
                    covered_lines=tuple(item["covered_lines"]),
                    executable_lines=tuple(item["executable_lines"]),
                    exit_code=item["exit_code"],
                    timed_out=item["timed_out"],
                    gcov_version=item["gcov_version"],
                    branches=tuple(
                        BranchCoverage(**branch)
                        for branch in item.get("branches", [])
                    ),
                )
                for item in value["tests"]
            ),
        )

    @property
    def executable_lines(self) -> tuple[int, ...]:
        return tuple(
            sorted({line for test in self.tests for line in test.executable_lines})
        )

    @property
    def passed_tests(self) -> int:
        return sum(test.verdict is TestVerdict.PASS for test in self.tests)

    @property
    def failed_tests(self) -> int:
        return sum(test.verdict is TestVerdict.FAIL for test in self.tests)

    @property
    def executable_branches(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            sorted(
                {
                    (branch.line, branch.branch_index)
                    for test in self.tests
                    for branch in test.branches
                }
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self)))


@dataclass(frozen=True)
class SpectrumLine:
    line: int
    ef: int
    ep: int
    nf: int
    np: int


@dataclass(frozen=True)
class SpectrumBranch:
    line: int
    branch_index: int
    ef: int
    ep: int
    nf: int
    np: int


@dataclass(frozen=True)
class RankedLine:
    rank: int
    line: int
    score: float
    ef: int
    ep: int
    nf: int
    np: int
    source_snippet: str
    tie_start_rank: int
    tie_end_rank: int
    branch_score: float | None = None


@dataclass(frozen=True)
class GroundTruth:
    case_id: str
    fault_lines: tuple[int, ...]
    source: str = "buggy_reference_diff"
    usage: str = "evaluation_only"
    mapping_rule: str = (
        "buggy_changed_lines; insertions_map_to_nearest_nonblank_context_"
        "preferring_previous"
    )

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self)))
