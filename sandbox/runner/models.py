"""Structured result models returned by the C++ runner."""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RunnerStatus(str, Enum):
    SUCCESS = "success"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class CompileResult:
    success: bool
    exit_code: int | None
    stdout: str
    stderr: str
    time_ms: int


@dataclass(frozen=True)
class RunResult:
    success: bool
    exit_code: int | None
    stdout: str
    stderr: str
    time_ms: int
    timed_out: bool


@dataclass(frozen=True)
class RunnerResult:
    status: RunnerStatus
    compile: CompileResult | None
    run: RunResult | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the result to a JSON-serializable dictionary."""

        result = asdict(self)
        result["status"] = self.status.value
        if result["error"] is None:
            result.pop("error")
        return result
