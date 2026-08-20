"""Build and validate the frozen Phase 9 formal patch corpus."""

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from benchmark.config import (
    PHASE8_ARTIFACT_ROOT,
    PHASE8_STAGE2_RESULT_MANIFEST,
    PROJECT_ROOT,
    REPAIR_ARTIFACT_ROOT,
)
from benchmark.frozen_artifacts import (
    FrozenArtifactError,
    artifact_groups_available,
    require_artifact_groups,
)
from repair.reporting import validate_frozen_repair_artifacts
from repair_phase8.partition import canonical_hash
from repair_phase8.protocol import validate_stage2_gate


PHASE7_ARTIFACT_SET_HASH = (
    "067710f9f3b71855cc4bf1db3dd0614cef89c1d4cec7e4f6e83c0372b7607f17"
)
PHASE8_STAGE1_ARTIFACT_SET_HASH = (
    "7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b"
)
PHASE8_STAGE2_ARTIFACT_SET_HASH = (
    "cf4f44f802913085ce70d7da344a3952c014295f712954b0de93d58ab2c96a04"
)
PHASE8_STAGE2_RESULT_HASH = (
    "bdc07d0be135edfc51e9c16c48c6163cead0cee6762654a30e0b76a483e4f95e"
)


def formal_patch_sources_available() -> bool:
    return artifact_groups_available(
        (
            (
                "Phase 7 formal repair artifacts",
                REPAIR_ARTIFACT_ROOT / "formal_evidence_ablation",
                "*/*/*.json",
                150,
            ),
            ("Phase 8 Initial artifacts", PHASE8_ARTIFACT_ROOT / "initial", "*/*.json", 100),
            ("Phase 8 Retry artifacts", PHASE8_ARTIFACT_ROOT / "retry_control", "*/*.json", 6),
            ("Phase 8 Feedback artifacts", PHASE8_ARTIFACT_ROOT / "feedback", "*/*.json", 6),
        )
    )


def require_formal_patch_sources() -> dict[str, list[Path]]:
    return require_artifact_groups(
        (
            (
                "Phase 7 formal repair artifacts",
                REPAIR_ARTIFACT_ROOT / "formal_evidence_ablation",
                "*/*/*.json",
                150,
            ),
            ("Phase 8 Initial artifacts", PHASE8_ARTIFACT_ROOT / "initial", "*/*.json", 100),
            ("Phase 8 Retry artifacts", PHASE8_ARTIFACT_ROOT / "retry_control", "*/*.json", 6),
            ("Phase 8 Feedback artifacts", PHASE8_ARTIFACT_ROOT / "feedback", "*/*.json", 6),
        )
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def finalize_corpus(
    entries: Iterable[dict[str, Any]], source_sets: dict[str, Any]
) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda item: item["patch_id"])
    patch_ids = [item["patch_id"] for item in ordered]
    artifact_ids = [
        (item["phase"], item["source_artifact_path"]) for item in ordered
    ]
    if len(patch_ids) != len(set(patch_ids)):
        raise ValueError("duplicate Phase 9 patch_id")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("duplicate Phase 9 source artifact identity")
    if any(not item.get("valid_output") or not item.get("patch_source_hash") for item in ordered):
        raise ValueError("Phase 9 corpus entries must contain extracted patches")
    value: dict[str, Any] = {
        "case_count": len({item["case_id"] for item in ordered}),
        "duplicate_patch_source_hashes": len(ordered)
        - len({item["patch_source_hash"] for item in ordered}),
        "entries": ordered,
        "patch_count": len(ordered),
        "protocol_version": "phase9-patch-corpus-v1",
        "source_sets": source_sets,
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def _entry(
    *,
    artifact_path: Path,
    record: dict[str, Any],
    patch_id: str,
    phase: str,
    arm: str,
) -> dict[str, Any] | None:
    source = (record.get("extraction") or {}).get("source")
    if not isinstance(source, str) or not source:
        return None
    evaluation = record.get("evaluation") or {}
    repair_time = record.get("repair_time_results") or {}
    return {
        "arm_or_group": arm,
        "case_id": record["case_id"],
        "compile_success": bool(evaluation.get("compile_success")),
        "hidden_validation_pass": bool(evaluation.get("validated")),
        "original_classification": record.get("classification"),
        "patch_id": patch_id,
        "patch_source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "phase": phase,
        "repair_time_pass": bool(
            evaluation.get("plausible")
            if phase == "phase7"
            else repair_time.get("success")
        ),
        "source_artifact_hash": sha256_file(artifact_path),
        "source_artifact_path": str(artifact_path.relative_to(PROJECT_ROOT)),
        "valid_output": True,
    }


def build_formal_patch_corpus() -> dict[str, Any]:
    require_formal_patch_sources()
    _phase7_records, phase7 = validate_frozen_repair_artifacts()
    if phase7["artifact_set_hash"] != PHASE7_ARTIFACT_SET_HASH:
        raise FrozenArtifactError("Frozen artifact hash mismatch: Phase 7 artifact set")
    stage2_gate = validate_stage2_gate()
    if stage2_gate["stage1"]["overall_manifest_hash"] != PHASE8_STAGE1_ARTIFACT_SET_HASH:
        raise ValueError("Phase 8 Stage 1 artifact-set hash mismatch")
    stage2_result = _record(PHASE8_STAGE2_RESULT_MANIFEST)
    claimed = stage2_result.get("overall_manifest_hash")
    unsigned = {key: item for key, item in stage2_result.items() if key != "overall_manifest_hash"}
    if claimed != PHASE8_STAGE2_RESULT_HASH or claimed != canonical_hash(unsigned):
        raise ValueError("Phase 8 Stage 2 result manifest hash mismatch")
    if stage2_result.get("artifact_set_hash") != PHASE8_STAGE2_ARTIFACT_SET_HASH:
        raise ValueError("Phase 8 Stage 2 artifact-set hash mismatch")

    entries = []
    attempted = {"phase7": 0, "phase8_initial": 0, "phase8_stage2": 0}
    phase7_root = REPAIR_ARTIFACT_ROOT / "formal_evidence_ablation"
    for path in sorted(phase7_root.glob("*/*/*.json")):
        record = _record(path)
        if record.get("experiment_role") != "formal_evidence_ablation":
            raise ValueError(f"non-formal Phase 7 artifact in formal root: {path}")
        if record.get("attempt") != 1 or record.get("experimental") is not True:
            raise ValueError(f"invalid Phase 7 formal artifact: {path}")
        attempted["phase7"] += 1
        item = _entry(
            artifact_path=path,
            record=record,
            patch_id=f"phase7/{record['case_id']}/{record['group']}",
            phase="phase7",
            arm=record["group"],
        )
        if item:
            entries.append(item)
    if attempted["phase7"] != 150:
        raise ValueError("Phase 7 corpus source must contain 150 formal attempts")

    for path in sorted((PHASE8_ARTIFACT_ROOT / "initial").glob("*/*.json")):
        record = _record(path)
        attempted["phase8_initial"] += 1
        item = _entry(
            artifact_path=path,
            record=record,
            patch_id=f"phase8-stage1/{record['case_id']}/Initial",
            phase="phase8_stage1",
            arm="Initial",
        )
        if item:
            if item["patch_source_hash"] != record.get("first_patch_hash"):
                raise ValueError(f"Phase 8 first patch hash mismatch: {path}")
            entries.append(item)
    if attempted["phase8_initial"] != 100:
        raise ValueError("Phase 8 Stage 1 corpus source must contain 100 attempts")

    stage2_by_identity = {
        (item["case_id"], item["arm"]): item for item in stage2_result["entries"]
    }
    for arm, label in (("retry_control", "R"), ("feedback", "F")):
        for path in sorted((PHASE8_ARTIFACT_ROOT / arm).glob("*/*.json")):
            record = _record(path)
            attempted["phase8_stage2"] += 1
            frozen = stage2_by_identity.get((record["case_id"], arm))
            if frozen is None or frozen["artifact_sha256"] != sha256_file(path):
                raise FrozenArtifactError(
                    f"Frozen artifact hash mismatch: Phase 8 Stage 2 raw artifact: {path}"
                )
            item = _entry(
                artifact_path=path,
                record=record,
                patch_id=f"phase8-stage2/{record['case_id']}/{label}",
                phase="phase8_stage2",
                arm=label,
            )
            if item:
                if item["patch_source_hash"] != record.get("second_patch_hash"):
                    raise ValueError(f"Phase 8 second patch hash mismatch: {path}")
                entries.append(item)
    if attempted["phase8_stage2"] != 12:
        raise ValueError("Phase 8 Stage 2 corpus source must contain 12 attempts")

    source_sets = {
        "attempted": attempted,
        "excluded_without_patch": {
            "phase7": attempted["phase7"]
            - sum(item["phase"] == "phase7" for item in entries),
            "phase8_initial": attempted["phase8_initial"]
            - sum(item["phase"] == "phase8_stage1" for item in entries),
            "phase8_stage2": attempted["phase8_stage2"]
            - sum(item["phase"] == "phase8_stage2" for item in entries),
        },
        "phase7_artifact_set_hash": PHASE7_ARTIFACT_SET_HASH,
        "phase8_stage1_artifact_set_hash": PHASE8_STAGE1_ARTIFACT_SET_HASH,
        "phase8_stage2_artifact_set_hash": PHASE8_STAGE2_ARTIFACT_SET_HASH,
        "phase8_stage2_result_manifest_hash": PHASE8_STAGE2_RESULT_HASH,
    }
    return finalize_corpus(entries, source_sets)


def load_patch_source(entry: dict[str, Any]) -> str:
    path = PROJECT_ROOT / entry["source_artifact_path"]
    record = _record(path)
    source = (record.get("extraction") or {}).get("source")
    if not isinstance(source, str):
        raise ValueError(f"missing patch source: {entry['patch_id']}")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != entry["patch_source_hash"]:
        raise ValueError(f"patch source hash mismatch: {entry['patch_id']}")
    return source
