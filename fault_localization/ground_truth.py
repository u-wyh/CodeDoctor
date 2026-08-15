"""Evaluation-only buggy/reference diff and buggy-side line mapping."""

from difflib import SequenceMatcher

from benchmark.models import BenchmarkCase

from .models import GroundTruth


def _insertion_context_line(lines: list[str], insertion_index: int) -> int | None:
    for index in range(insertion_index - 1, -1, -1):
        if lines[index].strip():
            return index + 1
    for index in range(insertion_index, len(lines)):
        if lines[index].strip():
            return index + 1
    return None


def derive_fault_lines(buggy_source: str, reference_source: str) -> tuple[int, ...]:
    buggy_lines = buggy_source.splitlines()
    reference_lines = reference_source.splitlines()
    matcher = SequenceMatcher(
        None, buggy_lines, reference_lines, autojunk=False
    )
    fault_lines: set[int] = set()
    for tag, buggy_start, buggy_end, _, _ in matcher.get_opcodes():
        if tag == "equal":
            continue
        if buggy_start < buggy_end:
            changed = {
                index + 1
                for index in range(buggy_start, buggy_end)
                if buggy_lines[index].strip()
            }
            if changed:
                fault_lines.update(changed)
            else:
                context_line = _insertion_context_line(
                    buggy_lines, buggy_start
                )
                if context_line is not None:
                    fault_lines.add(context_line)
            continue
        context_line = _insertion_context_line(buggy_lines, buggy_start)
        if context_line is not None:
            fault_lines.add(context_line)
    return tuple(sorted(fault_lines))


def build_ground_truth(case: BenchmarkCase) -> GroundTruth:
    return GroundTruth(
        case_id=case.case_id,
        fault_lines=derive_fault_lines(
            case.get_buggy_source(),
            case.get_reference_source(evaluation_only=True),
        ),
    )
