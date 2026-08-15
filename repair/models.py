"""Typed repair-time and evaluation-only boundaries."""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class EvidenceGroup(str, Enum):
    SOURCE_ONLY = "A"
    SOURCE_FL = "B"
    SOURCE_FL_EXECUTION = "C"


class PatchClassification(str, Enum):
    MODEL_ERROR = "model_error"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    COMPILE_ERROR = "compile_error"
    REPAIR_TEST_FAILED = "repair_test_failed"
    PLAUSIBLE_PATCH = "plausible_patch"
    VALIDATED_PATCH = "validated_patch"


@dataclass(frozen=True)
class SuspiciousLocation:
    rank: int
    line: int
    source_line: str
    line_score: float
    branch_score: float | None
    tie_start_rank: int
    tie_end_rank: int


@dataclass(frozen=True)
class TaskExample:
    test_id: str
    input_text: str
    expected_output: str


@dataclass(frozen=True)
class RepairTestEvidence:
    test_id: str
    verdict: str
    actual_stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


@dataclass(frozen=True)
class RepairContext:
    """The complete and auditable set of fields allowed into an LLM request."""

    case_id: str
    language: str
    buggy_source: str
    task_examples: tuple[TaskExample, ...]
    fl_status: str | None = None
    suspicious_locations: tuple[SuspiciousLocation, ...] = ()
    execution_evidence: tuple[RepairTestEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationContext:
    """Fields available only after generation; never accepted by prompt rendering."""

    case_id: str
    validation_test_ids: tuple[str, ...]
    reference_source_path: str
    ground_truth_fault_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class PromptDocument:
    template_version: str
    group: EvidenceGroup
    system: str
    user: str
    prompt_hash: str


@dataclass(frozen=True)
class ModelParameters:
    provider: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    seed: int | None = None

    def cache_view(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelResponse:
    text: str
    response_id: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    source: str | None
    strategy: str | None


@dataclass(frozen=True)
class TestResult:
    test_id: str
    passed: bool
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


@dataclass(frozen=True)
class PatchEvaluation:
    compile_success: bool
    compile_stdout: str
    compile_stderr: str
    compile_exit_code: int | None
    repair_tests: tuple[TestResult, ...]
    validation_tests: tuple[TestResult, ...]
    plausible: bool
    validated: bool
    classification: PatchClassification
    failure_modes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["classification"] = self.classification.value
        return value
