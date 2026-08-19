"""Build Phase 8 contexts and failed execution feedback."""

from pathlib import Path
from typing import Any

from benchmark.config import PROJECT_ROOT
from benchmark.models import BenchmarkCase
from repair.context import build_repair_context
from repair.models import EvidenceGroup, PatchEvaluation, RepairContext


def build_initial_context(
    case: BenchmarkCase,
    fl_record: dict[str, Any],
    frozen_buggy_evaluation: PatchEvaluation,
) -> RepairContext:
    return build_repair_context(
        case,
        EvidenceGroup.SOURCE_FL_EXECUTION,
        fl_record,
        frozen_buggy_evaluation,
    )


def _read(relative: str | None) -> str:
    if relative is None:
        return ""
    path = (PROJECT_ROOT / relative).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"Phase 8 test path escapes project root: {relative}")
    return path.read_text(encoding="utf-8", errors="replace")


def failed_execution_feedback(
    case: BenchmarkCase, evaluation: PatchEvaluation
) -> dict[str, object]:
    if not evaluation.compile_success:
        return {
            "compile": {
                "exit_code": evaluation.compile_exit_code,
                "stderr": evaluation.compile_stderr,
            },
            "failed_tests": [],
        }
    tests = {item.test_id: item for item in case.tests.repair_tests}
    failed = []
    for result in evaluation.repair_tests:
        if result.passed:
            continue
        test = tests[result.test_id]
        failed.append(
            {
                "actual_stdout": result.stdout,
                "exit_code": result.exit_code,
                "expected_output": _read(test.expected_output_path),
                "input": _read(test.input_path),
                "stderr": result.stderr,
                "test_id": result.test_id,
                "timed_out": result.timed_out,
                "verdict": "FAIL",
            }
        )
    return {"compile": None, "failed_tests": failed}
