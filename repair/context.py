"""Construct group-specific RepairContext without opening evaluation-only files."""

import json
from pathlib import Path
from typing import Any

from benchmark.models import BenchmarkCase
from benchmark.config import PROJECT_ROOT

from .evaluator import repair_execution_evidence
from .models import (
    EvidenceGroup,
    PatchEvaluation,
    RepairContext,
    SuspiciousLocation,
    TaskExample,
)


def load_fl_records(path: Path) -> dict[str, dict[str, Any]]:
    return {
        item["case_id"]: item
        for item in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def build_repair_context(
    case: BenchmarkCase,
    group: EvidenceGroup,
    fl_record: dict[str, Any] | None,
    buggy_evaluation: PatchEvaluation | None,
) -> RepairContext:
    task_examples = []
    for test in case.tests.repair_tests:
        input_path = (PROJECT_ROOT / str(test.input_path)).resolve()
        output_path = (PROJECT_ROOT / str(test.expected_output_path)).resolve()
        if not input_path.is_relative_to(PROJECT_ROOT.resolve()) or not output_path.is_relative_to(
            PROJECT_ROOT.resolve()
        ):
            raise ValueError(f"repair-time oracle path escapes project root: {test.test_id}")
        task_examples.append(
            TaskExample(
                test_id=test.test_id,
                input_text=input_path.read_text(encoding="utf-8", errors="replace"),
                expected_output=output_path.read_text(
                    encoding="utf-8", errors="replace"
                ),
            )
        )
    locations = ()
    evidence = ()
    fl_status = None
    if group in {EvidenceGroup.SOURCE_FL, EvidenceGroup.SOURCE_FL_EXECUTION}:
        if fl_record is None or fl_record.get("method_version") != "fl-v1":
            raise ValueError(f"frozen FL-v1 evidence missing for {case.case_id}")
        fl_status = str(fl_record["availability_message"])
        locations = tuple(
            SuspiciousLocation(**item) for item in fl_record["locations"]
        )
    if group is EvidenceGroup.SOURCE_FL_EXECUTION:
        if buggy_evaluation is None or not buggy_evaluation.compile_success:
            raise ValueError(f"buggy execution evidence missing for {case.case_id}")
        evidence = repair_execution_evidence(case, buggy_evaluation)
    return RepairContext(
        case_id=case.case_id,
        language=case.language,
        buggy_source=case.get_buggy_source(),
        task_examples=tuple(task_examples),
        fl_status=fl_status,
        suspicious_locations=locations,
        execution_evidence=evidence,
    )
