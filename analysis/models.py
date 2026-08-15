"""Unified bug evidence produced by CodeDoctor analyzers."""

from dataclasses import asdict, dataclass, field
from typing import Any

from sandbox.runner.models import RunnerResult


@dataclass(frozen=True)
class SourceLocation:
    file: str | None
    line: int | None
    column: int | None


@dataclass(frozen=True)
class StackFrame:
    index: int
    function: str | None
    file: str | None
    line: int | None
    column: int | None
    address: str | None
    is_user_code: bool


@dataclass(frozen=True)
class MemoryAccess:
    operation: str | None
    size: int | None
    address: str | None


@dataclass(frozen=True)
class BugEvidence:
    analyzer: str
    category: str
    severity: str
    summary: str
    message: str
    location: SourceLocation | None
    function: str | None
    stack_trace: list[StackFrame]
    raw_report: str
    memory_access: MemoryAccess | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisResult:
    mode: str
    runner: RunnerResult
    evidence: list[BugEvidence]

    def to_dict(self) -> dict[str, Any]:
        result = self.runner.to_dict()
        result["analysis"] = {
            "mode": self.mode,
            "evidence_count": len(self.evidence),
            "evidence": [item.to_dict() for item in self.evidence],
        }
        return result
