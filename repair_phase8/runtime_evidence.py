"""Freeze and validate buggy runtime evidence for the Phase 8 Evaluation Set."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from benchmark.config import (
    PHASE8_EVALUATION_SET,
    PHASE8_PROTOCOL,
    PHASE8_RUNTIME_MANIFEST,
    PHASE8_RUNTIME_ROOT,
    PHASE8_TEST_PARTITION,
    PROJECT_ROOT,
)
from benchmark.models import BenchmarkCase
from repair.evaluator import evaluate_source
from repair.models import PatchEvaluation
from repair.runtime_evidence import (
    RUNTIME_EVIDENCE_PROTOCOL_VERSION,
    _canonical_bytes,
    _evaluation_from_snapshot,
    _relative_path,
    _sha256_bytes,
    _snapshot_document,
    _write_json,
    runner_metadata,
)


PHASE8_RUNTIME_PROTOCOL = "phase8-runtime-evidence-v1"


@dataclass(frozen=True)
class Phase8FrozenRuntime:
    evaluations: dict[str, PatchEvaluation]
    manifest: dict[str, Any]
    validation: dict[str, Any]


def _project_path(relative: str, root: Path) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Phase 8 runtime path escapes project root: {relative}")
    return path


def _manifest_hash(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def freeze_phase8_runtime(
    cases: Sequence[BenchmarkCase],
    *,
    artifact_root: Path = PHASE8_RUNTIME_ROOT,
    manifest_path: Path = PHASE8_RUNTIME_MANIFEST,
    capture: Callable[[BenchmarkCase], PatchEvaluation] | None = None,
    backend_metadata: dict[str, Any] | None = None,
    generated_at: str | None = None,
    project_root: Path = PROJECT_ROOT,
    force: bool = False,
) -> Phase8FrozenRuntime:
    if manifest_path.exists() and not force:
        raise FileExistsError(f"Phase 8 runtime manifest already exists: {manifest_path}")
    if force:
        manifest_path.unlink(missing_ok=True)
        shutil.rmtree(artifact_root, ignore_errors=True)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    run = capture or (
        lambda case: evaluate_source(
            case, case.get_buggy_source(project_root), include_validation=False
        )
    )
    entries = []
    for order, case in enumerate(cases):
        evaluation = run(case)
        document = _snapshot_document(case, evaluation, timestamp)
        artifact = artifact_root / f"{case.case_id}.json"
        _write_json(artifact, document)
        entries.append(
            {
                "case_id": case.case_id,
                "order": order,
                "path": _relative_path(artifact, project_root),
                "repair_test_ids": [item.test_id for item in case.tests.repair_tests],
                "sha256": _sha256_bytes(artifact.read_bytes()),
            }
        )
    protocol = json.loads(PHASE8_PROTOCOL.read_text(encoding="utf-8"))
    partition = json.loads(PHASE8_TEST_PARTITION.read_text(encoding="utf-8"))
    manifest: dict[str, Any] = {
        "artifacts": entries,
        "capture_rule": {
            "buggy_executions_per_repair_test": 1,
            "normalization": "none",
            "order": "Phase 8 Evaluation Set and partition manifest order",
            "selection": "first and only observation",
            "transport_retries": 0,
        },
        "evaluation_set": {
            "case_count": len(cases),
            "path": _relative_path(PHASE8_EVALUATION_SET, project_root),
            "sha256": _sha256_bytes(PHASE8_EVALUATION_SET.read_bytes()),
        },
        "generated_at": timestamp,
        "phase8_protocol": {
            "path": _relative_path(PHASE8_PROTOCOL, project_root),
            "protocol_version": protocol["protocol_version"],
            "sha256": _sha256_bytes(PHASE8_PROTOCOL.read_bytes()),
        },
        "protocol_version": PHASE8_RUNTIME_PROTOCOL,
        "runner": backend_metadata or runner_metadata(),
        "snapshot_format": RUNTIME_EVIDENCE_PROTOCOL_VERSION,
        "test_partition": {
            "overall_manifest_hash": partition["overall_manifest_hash"],
            "path": _relative_path(PHASE8_TEST_PARTITION, project_root),
            "sha256": _sha256_bytes(PHASE8_TEST_PARTITION.read_bytes()),
        },
    }
    manifest["overall_manifest_hash"] = _manifest_hash(manifest)
    _write_json(manifest_path, manifest)
    return load_phase8_runtime(cases, manifest_path=manifest_path, project_root=project_root)


def load_phase8_runtime(
    cases: Sequence[BenchmarkCase],
    *,
    manifest_path: Path = PHASE8_RUNTIME_MANIFEST,
    project_root: Path = PROJECT_ROOT,
) -> Phase8FrozenRuntime:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Phase 8 runtime manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != PHASE8_RUNTIME_PROTOCOL:
        raise ValueError("Phase 8 runtime protocol mismatch")
    if manifest.get("overall_manifest_hash") != _manifest_hash(manifest):
        raise ValueError("Phase 8 runtime manifest hash mismatch")
    for key, expected_path in (
        ("evaluation_set", PHASE8_EVALUATION_SET),
        ("phase8_protocol", PHASE8_PROTOCOL),
        ("test_partition", PHASE8_TEST_PARTITION),
    ):
        value = manifest[key]
        path = _project_path(value["path"], project_root)
        if path != expected_path.resolve() or value["sha256"] != _sha256_bytes(path.read_bytes()):
            raise ValueError(f"Phase 8 runtime {key} hash mismatch")
    protocol = json.loads(PHASE8_PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "phase8-v1":
        raise ValueError("Phase 8 protocol version mismatch")
    partition = json.loads(PHASE8_TEST_PARTITION.read_text(encoding="utf-8"))
    if (
        manifest["test_partition"]["overall_manifest_hash"]
        != partition.get("overall_manifest_hash")
    ):
        raise ValueError("Phase 8 partition manifest binding mismatch")
    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise ValueError("Phase 8 runtime evidence coverage mismatch")
    evaluations = {}
    test_count = 0
    for order, (case, entry) in enumerate(zip(cases, entries)):
        expected_ids = [item.test_id for item in case.tests.repair_tests]
        if (
            entry.get("order") != order
            or entry.get("case_id") != case.case_id
            or entry.get("repair_test_ids") != expected_ids
        ):
            raise ValueError(f"Phase 8 runtime order mismatch for {case.case_id}")
        artifact = _project_path(entry["path"], project_root)
        content = artifact.read_bytes()
        if entry.get("sha256") != _sha256_bytes(content):
            raise ValueError(f"Phase 8 runtime artifact hash mismatch for {case.case_id}")
        evaluations[case.case_id] = _evaluation_from_snapshot(
            case, json.loads(content)
        )
        test_count += len(expected_ids)
    validation = {
        "case_count": len(evaluations),
        "manifest_hash": manifest["overall_manifest_hash"],
        "repair_test_count": test_count,
        "status": "passed",
    }
    return Phase8FrozenRuntime(evaluations, manifest, validation)
