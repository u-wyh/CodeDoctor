"""Capture and validate preregistered runtime evidence for formal repair prompts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from benchmark.config import (
    BENCHMARK_COMPILE_TIMEOUT_SECONDS,
    BENCHMARK_RUN_TIMEOUT_SECONDS,
    CODEFLAWS_REPAIR_PILOT,
    PROJECT_ROOT,
    REPAIR_PROTOCOL,
    RUNTIME_EVIDENCE_MANIFEST,
    RUNTIME_EVIDENCE_ROOT,
)
from benchmark.models import BenchmarkCase
from sandbox.runner.config import RunnerConfig
from sandbox.runner.docker_executor import check_docker

from .evaluator import evaluate_source
from .models import PatchClassification, PatchEvaluation, TestResult


RUNTIME_EVIDENCE_PROTOCOL_VERSION = "runtime-evidence-v1"
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class FrozenRuntimeEvidence:
    evaluations: dict[str, PatchEvaluation]
    manifest: dict[str, Any]
    validation: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _relative_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    root = project_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"runtime evidence path escapes project root: {path}")
    return str(resolved.relative_to(root))


def _project_path(relative: str, project_root: Path) -> Path:
    path = (project_root / relative).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise ValueError(f"runtime evidence path escapes project root: {relative}")
    return path


def runner_metadata(config: RunnerConfig | None = None) -> dict[str, Any]:
    active = config or RunnerConfig()
    docker = check_docker(active, PROJECT_ROOT)
    inspected = subprocess.run(
        [docker, "image", "inspect", active.docker_image, "--format", "{{.Id}}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "backend": active.backend,
        "compile_timeout_seconds": BENCHMARK_COMPILE_TIMEOUT_SECONDS,
        "docker_image": active.docker_image,
        "docker_image_id": inspected.stdout.strip(),
        "execution_policy": {
            "cap_drop": "ALL",
            "cpus": 1.0,
            "memory": "256m",
            "network": "none",
            "no_new_privileges": True,
            "pids_limit": 64,
            "read_only": True,
        },
        "repair_test_order": "Repair Pilot manifest order",
        "run_timeout_seconds": BENCHMARK_RUN_TIMEOUT_SECONDS,
        "transport_retries": 0,
    }


def runtime_observation_view(evaluation: PatchEvaluation) -> dict[str, Any]:
    return {
        "repair_tests": [
            {
                "exit_code": item.exit_code,
                "passed": item.passed,
                "stderr": item.stderr,
                "stdout": item.stdout,
                "test_id": item.test_id,
                "timed_out": item.timed_out,
            }
            for item in evaluation.repair_tests
        ]
    }


def runtime_observation_hash(evaluation: PatchEvaluation) -> str:
    return _sha256_bytes(_canonical_bytes(runtime_observation_view(evaluation)))


def _snapshot_document(
    case: BenchmarkCase,
    evaluation: PatchEvaluation,
    generated_at: str,
) -> dict[str, Any]:
    expected_ids = [test.test_id for test in case.tests.repair_tests]
    actual_ids = [test.test_id for test in evaluation.repair_tests]
    if expected_ids != actual_ids:
        raise ValueError(
            f"repair test order mismatch while capturing {case.case_id}: "
            f"expected {expected_ids}, got {actual_ids}"
        )
    if not evaluation.compile_success:
        raise ValueError(f"buggy source did not compile while capturing {case.case_id}")
    tests = []
    for order, item in enumerate(evaluation.repair_tests):
        tests.append(
            {
                "exit_code": item.exit_code,
                "order": order,
                "passed": item.passed,
                "stderr": item.stderr,
                "stderr_utf8_sha256": _sha256_text(item.stderr),
                "stdout": item.stdout,
                "stdout_utf8_sha256": _sha256_text(item.stdout),
                "test_id": item.test_id,
                "timed_out": item.timed_out,
            }
        )
    return {
        "case_id": case.case_id,
        "compile": {
            "exit_code": evaluation.compile_exit_code,
            "stderr": evaluation.compile_stderr,
            "stderr_utf8_sha256": _sha256_text(evaluation.compile_stderr),
            "stdout": evaluation.compile_stdout,
            "stdout_utf8_sha256": _sha256_text(evaluation.compile_stdout),
            "success": evaluation.compile_success,
        },
        "generated_at": generated_at,
        "protocol_version": RUNTIME_EVIDENCE_PROTOCOL_VERSION,
        "repair_tests": tests,
        "schema_version": SCHEMA_VERSION,
    }


def _manifest_hash(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def freeze_runtime_evidence(
    cases: Sequence[BenchmarkCase],
    *,
    artifact_root: Path = RUNTIME_EVIDENCE_ROOT,
    manifest_path: Path = RUNTIME_EVIDENCE_MANIFEST,
    pilot_path: Path = CODEFLAWS_REPAIR_PILOT,
    repair_protocol_path: Path = REPAIR_PROTOCOL,
    project_root: Path = PROJECT_ROOT,
    capture: Callable[[BenchmarkCase], PatchEvaluation] | None = None,
    backend_metadata: dict[str, Any] | None = None,
    generated_at: str | None = None,
    force: bool = False,
) -> FrozenRuntimeEvidence:
    if manifest_path.exists() and not force:
        raise FileExistsError(
            f"runtime evidence manifest already exists: {manifest_path}; use force explicitly"
        )
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    evaluate = capture or (
        lambda case: evaluate_source(
            case,
            case.get_buggy_source(project_root),
            include_validation=False,
        )
    )
    metadata = backend_metadata or runner_metadata()
    entries = []
    for order, case in enumerate(cases):
        evaluation = evaluate(case)
        document = _snapshot_document(case, evaluation, timestamp)
        artifact_path = artifact_root / f"{case.case_id}.json"
        _write_json(artifact_path, document)
        entries.append(
            {
                "case_id": case.case_id,
                "order": order,
                "path": _relative_path(artifact_path, project_root),
                "repair_test_ids": [test.test_id for test in case.tests.repair_tests],
                "sha256": _sha256_bytes(artifact_path.read_bytes()),
            }
        )
    protocol_document = json.loads(repair_protocol_path.read_text(encoding="utf-8"))
    manifest = {
        "artifacts": entries,
        "capture_rule": {
            "buggy_executions_per_repair_test": 1,
            "case_order": "Repair Pilot manifest order",
            "normalization": "none",
            "repair_test_order": "manifest-defined order",
            "selection": "first and only observation",
            "transport_retries": 0,
        },
        "generated_at": timestamp,
        "protocol_version": RUNTIME_EVIDENCE_PROTOCOL_VERSION,
        "repair_pilot": {
            "case_count": len(cases),
            "path": _relative_path(pilot_path, project_root),
            "sha256": _sha256_bytes(pilot_path.read_bytes()),
        },
        "repair_protocol": {
            "path": _relative_path(repair_protocol_path, project_root),
            "protocol_version": protocol_document.get("protocol_version"),
            "sha256": _sha256_bytes(repair_protocol_path.read_bytes()),
        },
        "runner": metadata,
        "schema_version": SCHEMA_VERSION,
    }
    manifest["overall_manifest_hash"] = _manifest_hash(manifest)
    _write_json(manifest_path, manifest)
    return load_frozen_runtime_evidence(
        cases,
        manifest_path=manifest_path,
        project_root=project_root,
    )


def _evaluation_from_snapshot(
    case: BenchmarkCase, document: dict[str, Any]
) -> PatchEvaluation:
    if document.get("protocol_version") != RUNTIME_EVIDENCE_PROTOCOL_VERSION:
        raise ValueError(f"runtime evidence protocol mismatch for {case.case_id}")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"runtime evidence schema mismatch for {case.case_id}")
    if document.get("case_id") != case.case_id:
        raise ValueError(f"runtime evidence case mismatch for {case.case_id}")
    compile_value = document.get("compile", {})
    if compile_value.get("success") is not True:
        raise ValueError(f"frozen buggy compile failed for {case.case_id}")
    for field in ("stdout", "stderr"):
        text = compile_value.get(field)
        if not isinstance(text, str) or compile_value.get(f"{field}_utf8_sha256") != _sha256_text(text):
            raise ValueError(f"compile {field} hash mismatch for {case.case_id}")
    expected_ids = [test.test_id for test in case.tests.repair_tests]
    values = document.get("repair_tests")
    if not isinstance(values, list) or len(values) != len(expected_ids):
        raise ValueError(f"repair test snapshot count mismatch for {case.case_id}")
    tests = []
    for order, (expected_id, item) in enumerate(zip(expected_ids, values)):
        if item.get("order") != order or item.get("test_id") != expected_id:
            raise ValueError(f"repair test snapshot order mismatch for {case.case_id}")
        if not isinstance(item.get("passed"), bool) or not isinstance(
            item.get("timed_out"), bool
        ):
            raise ValueError(f"runtime evidence status type mismatch for {case.case_id}")
        exit_code = item.get("exit_code")
        if exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            raise ValueError(f"runtime evidence exit code type mismatch for {case.case_id}")
        for field in ("stdout", "stderr"):
            text = item.get(field)
            if not isinstance(text, str) or item.get(f"{field}_utf8_sha256") != _sha256_text(text):
                raise ValueError(
                    f"runtime evidence {field} hash mismatch for {case.case_id}/{expected_id}"
                )
        tests.append(
            TestResult(
                test_id=expected_id,
                passed=item["passed"],
                stdout=item["stdout"],
                stderr=item["stderr"],
                exit_code=exit_code,
                timed_out=item["timed_out"],
            )
        )
    repair_tests = tuple(tests)
    plausible = bool(repair_tests) and all(item.passed for item in repair_tests)
    classification = (
        PatchClassification.PLAUSIBLE_PATCH
        if plausible
        else PatchClassification.REPAIR_TEST_FAILED
    )
    failure_modes = () if plausible else ("repair_test_failed",)
    return PatchEvaluation(
        compile_success=True,
        compile_stdout=compile_value["stdout"],
        compile_stderr=compile_value["stderr"],
        compile_exit_code=compile_value.get("exit_code"),
        repair_tests=repair_tests,
        validation_tests=(),
        plausible=plausible,
        validated=False,
        classification=classification,
        failure_modes=failure_modes,
    )


def load_frozen_runtime_evidence(
    cases: Sequence[BenchmarkCase],
    *,
    manifest_path: Path = RUNTIME_EVIDENCE_MANIFEST,
    project_root: Path = PROJECT_ROOT,
) -> FrozenRuntimeEvidence:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"frozen runtime evidence manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != RUNTIME_EVIDENCE_PROTOCOL_VERSION:
        raise ValueError("frozen runtime evidence protocol mismatch")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("frozen runtime evidence schema mismatch")
    if manifest.get("overall_manifest_hash") != _manifest_hash(manifest):
        raise ValueError("frozen runtime evidence manifest hash mismatch")
    pilot = manifest.get("repair_pilot", {})
    pilot_path = _project_path(str(pilot.get("path", "")), project_root)
    if not pilot_path.is_file() or pilot.get("sha256") != _sha256_bytes(pilot_path.read_bytes()):
        raise ValueError("Repair Pilot manifest hash mismatch")
    repair_protocol = manifest.get("repair_protocol", {})
    repair_protocol_path = _project_path(
        str(repair_protocol.get("path", "")), project_root
    )
    if (
        not repair_protocol_path.is_file()
        or repair_protocol.get("sha256")
        != _sha256_bytes(repair_protocol_path.read_bytes())
    ):
        raise ValueError("repair protocol hash mismatch in runtime evidence manifest")
    protocol_document = json.loads(repair_protocol_path.read_text(encoding="utf-8"))
    if (
        repair_protocol.get("protocol_version") != "repair-v2"
        or protocol_document.get("protocol_version") != "repair-v2"
    ):
        raise ValueError("repair-v2 protocol mismatch in runtime evidence manifest")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise ValueError("frozen runtime evidence does not cover every Repair Pilot case")
    evaluations = {}
    test_count = 0
    for order, (case, entry) in enumerate(zip(cases, entries)):
        expected_ids = [test.test_id for test in case.tests.repair_tests]
        if (
            entry.get("order") != order
            or entry.get("case_id") != case.case_id
            or entry.get("repair_test_ids") != expected_ids
        ):
            raise ValueError(f"runtime evidence manifest order mismatch for {case.case_id}")
        artifact_path = _project_path(str(entry.get("path", "")), project_root)
        if not artifact_path.is_file():
            raise FileNotFoundError(
                f"frozen runtime evidence snapshot missing for {case.case_id}: {artifact_path}"
            )
        artifact_bytes = artifact_path.read_bytes()
        if entry.get("sha256") != _sha256_bytes(artifact_bytes):
            raise ValueError(f"runtime evidence artifact hash mismatch for {case.case_id}")
        document = json.loads(artifact_bytes)
        evaluations[case.case_id] = _evaluation_from_snapshot(case, document)
        test_count += len(expected_ids)
    validation = {
        "case_count": len(evaluations),
        "manifest_hash": manifest["overall_manifest_hash"],
        "protocol_version": RUNTIME_EVIDENCE_PROTOCOL_VERSION,
        "repair_test_count": test_count,
        "status": "passed",
    }
    return FrozenRuntimeEvidence(evaluations, manifest, validation)
