"""Layered parser for GCC/Clang ASan, LSan, and UBSan text reports."""

import re
from pathlib import PurePosixPath

from analysis.models import BugEvidence, MemoryAccess, SourceLocation, StackFrame


_ASAN_HEADER = re.compile(
    r"(?:==\d+==)?ERROR: "
    r"(?P<analyzer>AddressSanitizer|LeakSanitizer): "
    r"(?P<message>[^\n]+)"
)
_UBSAN_HEADER = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+): "
    r"runtime error: (?P<message>[^\n]+)$",
    re.MULTILINE,
)
_FRAME = re.compile(
    r"^\s*#(?P<index>\d+)\s+"
    r"(?P<address>0x[0-9a-fA-F]+)"
    r"(?:\s+in\s+(?P<body>.+)|\s+(?P<body_without_in>.+))?$"
)
_LOCATION_AT_END = re.compile(
    r"(?P<file>[^\s:]+):(?P<line>\d+)(?::(?P<column>\d+))?$"
)
_MEMORY_ACCESS = re.compile(
    r"\b(?P<operation>READ|WRITE) of size (?P<size>\d+) "
    r"at (?P<address>0x[0-9a-fA-F]+)"
)


class SanitizerParser:
    """Parse zero or more sanitizer diagnostics without trusting exit codes."""

    def parse(self, report: str) -> list[BugEvidence]:
        if not report:
            return []

        evidence: list[BugEvidence] = []
        evidence.extend(self._parse_ubsan(report))
        evidence.extend(self._parse_asan(report))
        return sorted(evidence, key=lambda item: self._report_position(report, item))

    @staticmethod
    def _report_position(report: str, evidence: BugEvidence) -> int:
        if evidence.analyzer == "ubsan" and evidence.location is not None:
            marker = f"{evidence.location.line}:{evidence.location.column}: runtime error"
            position = report.find(marker)
            if position >= 0:
                return position
        position = report.find(evidence.message)
        return position if position >= 0 else len(report)

    def _parse_asan(self, report: str) -> list[BugEvidence]:
        matches = list(_ASAN_HEADER.finditer(report))
        evidence: list[BugEvidence] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(report)
            section = report[match.start():end]
            message = match.group("message").strip()
            category = self._asan_category(message)
            frames = self._primary_stack(section)
            user_frame = next((frame for frame in frames if frame.is_user_code), None)
            location = self._location_from_frame(user_frame)
            memory_access = self._memory_access(section)
            analyzer = (
                "lsan"
                if match.group("analyzer") == "LeakSanitizer"
                else "asan"
            )
            evidence.append(
                BugEvidence(
                    analyzer=analyzer,
                    category=category,
                    severity="error",
                    summary=category,
                    message=message,
                    location=location,
                    function=user_frame.function if user_frame else None,
                    stack_trace=frames,
                    raw_report=report,
                    memory_access=memory_access,
                )
            )
        if not matches and "AddressSanitizer:DEADLYSIGNAL" in report:
            frames = self._primary_stack(report)
            user_frame = next((frame for frame in frames if frame.is_user_code), None)
            evidence.append(
                BugEvidence(
                    analyzer="asan",
                    category="unknown",
                    severity="error",
                    summary="AddressSanitizer fatal signal",
                    message="DEADLYSIGNAL",
                    location=self._location_from_frame(user_frame),
                    function=user_frame.function if user_frame else None,
                    stack_trace=frames,
                    raw_report=report,
                )
            )
        return evidence

    def _parse_ubsan(self, report: str) -> list[BugEvidence]:
        matches = list(_UBSAN_HEADER.finditer(report))
        evidence: list[BugEvidence] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(report)
            section = report[match.end():end]
            message = match.group("message").strip()
            frames = self._primary_stack(section)
            user_frame = next((frame for frame in frames if frame.is_user_code), None)
            file_name = self._normalize_file(match.group("file"))
            function = user_frame.function if user_frame else None
            evidence.append(
                BugEvidence(
                    analyzer="ubsan",
                    category=self._ubsan_category(message),
                    severity="error",
                    summary=self._ubsan_category(message),
                    message=message,
                    location=SourceLocation(
                        file=file_name,
                        line=int(match.group("line")),
                        column=int(match.group("column")),
                    ),
                    function=function,
                    stack_trace=frames,
                    raw_report=report,
                    metadata={"runtime_error": message},
                )
            )
        return evidence

    def _primary_stack(self, section: str) -> list[StackFrame]:
        frames: list[StackFrame] = []
        started = False
        for line in section.splitlines():
            frame = self._parse_frame(line)
            if frame is not None:
                started = True
                frames.append(frame)
            elif started:
                break
        return frames

    def _parse_frame(self, line: str) -> StackFrame | None:
        match = _FRAME.match(line)
        if match is None:
            return None

        body = match.group("body") or match.group("body_without_in") or ""
        location_match = _LOCATION_AT_END.search(body)
        if location_match is None:
            function = body.strip() or None
            file_name = None
            line_number = None
            column = None
        else:
            function = body[:location_match.start()].strip() or None
            file_name = self._normalize_file(location_match.group("file"))
            line_number = int(location_match.group("line"))
            column_text = location_match.group("column")
            column = int(column_text) if column_text else None

        return StackFrame(
            index=int(match.group("index")),
            function=function,
            file=file_name,
            line=line_number,
            column=column,
            address=match.group("address"),
            is_user_code=file_name == "main.cpp",
        )

    @staticmethod
    def _normalize_file(file_name: str) -> str:
        normalized = file_name.replace("\\", "/")
        workspace_prefix = "/workspace/"
        if normalized.startswith(workspace_prefix):
            return normalized[len(workspace_prefix):]
        if PurePosixPath(normalized).name == "main.cpp":
            return "main.cpp"
        return normalized

    @staticmethod
    def _location_from_frame(frame: StackFrame | None) -> SourceLocation | None:
        if frame is None:
            return None
        return SourceLocation(frame.file, frame.line, frame.column)

    @staticmethod
    def _memory_access(section: str) -> MemoryAccess | None:
        match = _MEMORY_ACCESS.search(section)
        if match is None:
            return None
        return MemoryAccess(
            operation=match.group("operation"),
            size=int(match.group("size")),
            address=match.group("address"),
        )

    @staticmethod
    def _asan_category(message: str) -> str:
        lowered = message.lower()
        for category in (
            "heap-buffer-overflow",
            "stack-buffer-overflow",
            "global-buffer-overflow",
            "heap-use-after-free",
            "stack-use-after-return",
            "stack-use-after-scope",
            "double-free",
            "alloc-dealloc-mismatch",
        ):
            if category in lowered:
                return category
        if "detected memory leaks" in lowered or "byte(s) leaked" in lowered:
            return "memory-leak"
        return "unknown"

    @staticmethod
    def _ubsan_category(message: str) -> str:
        lowered = message.lower()
        if "signed integer overflow" in lowered:
            return "signed-integer-overflow"
        if "division by zero" in lowered or "divide by zero" in lowered:
            return "division-by-zero"
        if "shift" in lowered and (
            "too large" in lowered
            or "negative" in lowered
            or "cannot be represented" in lowered
        ):
            return "invalid-shift"
        if "null pointer" in lowered:
            return "null-pointer-access"
        if "misaligned address" in lowered:
            return "misaligned-address"
        if "out of bounds" in lowered:
            return "out-of-bounds"
        if "insufficient space for an object" in lowered:
            return "out-of-bounds"
        return "unknown"
