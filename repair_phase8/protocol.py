"""Phase 8 preflight and two-stage fail-closed gates."""

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from benchmark.config import (
    PHASE8_ELIGIBLE_COHORT,
    PHASE8_ARTIFACT_ROOT,
    PHASE8_EVALUATION_SET,
    PHASE8_FL,
    PHASE8_PAYLOAD_ATTRIBUTION,
    PHASE8_PROMPT_AUDIT,
    PHASE8_PROTOCOL,
    PHASE8_RENDER_PROTOCOL,
    PHASE8_RUNTIME_MANIFEST,
    PHASE8_STAGE1_MANIFEST,
    PHASE8_TEST_PARTITION,
)
from benchmark.models import BenchmarkCase, load_manifest

from .partition import canonical_hash, load_partition_manifest
from .runtime_evidence import load_phase8_runtime


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_phase8_preflight() -> dict[str, Any]:
    protocol = json.loads(PHASE8_PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "phase8-v1":
        raise ValueError("Phase 8 protocol mismatch")
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    if len(cases) != 100 or len({case.case_id for case in cases}) != 100:
        raise ValueError("Phase 8 Evaluation Set must contain 100 unique cases")
    partition = load_partition_manifest(PHASE8_TEST_PARTITION)
    if partition.get("case_count") != 100:
        raise ValueError("Phase 8 partition must cover 100 cases")
    partition_ids = [item["case_id"] for item in partition["partitions"]]
    if partition_ids != [case.case_id for case in cases]:
        raise ValueError("Phase 8 partition case order mismatch")
    fl = _read_jsonl(PHASE8_FL)
    if [item["case_id"] for item in fl] != [case.case_id for case in cases]:
        raise ValueError("Phase 8 FL-v1 coverage/order mismatch")
    if any(item.get("method_version") != "fl-v1" for item in fl):
        raise ValueError("Phase 8 FL method version mismatch")
    runtime = load_phase8_runtime(cases)
    prompt_audit = json.loads(PHASE8_PROMPT_AUDIT.read_text(encoding="utf-8"))
    attribution = json.loads(PHASE8_PAYLOAD_ATTRIBUTION.read_text(encoding="utf-8"))
    render_protocol = json.loads(PHASE8_RENDER_PROTOCOL.read_text(encoding="utf-8"))
    prompt_records = prompt_audit.get("prompt_records", [])
    hard_gate = render_protocol.get("hard_serialized_payload_bytes")
    if (
        prompt_audit.get("protocol_version") != "phase8-initial-prompt-audit-v2"
        or prompt_audit.get("prompts_checked") != 100
        or not prompt_audit.get("hashes_identical_across_reloads")
        or prompt_audit.get("leakage_audit", {}).get("status") != "passed"
        or prompt_audit.get("operational_size_gate", {}).get("status") != "passed"
        or prompt_audit.get("runtime_manifest_hash")
        != runtime.validation["manifest_hash"]
        or prompt_audit.get("partition_manifest_hash")
        != partition["overall_manifest_hash"]
        or prompt_audit.get("render_protocol", {}).get("protocol_version")
        != "phase8-runtime-evidence-render-v2"
        or prompt_audit.get("render_protocol", {}).get("sha256")
        != _sha256(PHASE8_RENDER_PROTOCOL)
        or render_protocol.get("protocol_version")
        != "phase8-runtime-evidence-render-v2"
        or not prompt_audit.get("reproducibility", {}).get(
            "random_order_reload_equal"
        )
        or len(prompt_audit.get("oversized_case_stress", [])) != 4
        or not all(
            item.get("hashes_identical_10_of_10")
            for item in prompt_audit.get("oversized_case_stress", [])
        )
        or attribution.get("case_count") != 100
        or attribution.get("oversized_case_count") != 4
        or attribution.get("superseded_prompt_set_hash")
        != prompt_audit.get("superseded_prompt_set_hash")
        or len(prompt_records) != 100
        or [item.get("case_id") for item in prompt_records]
        != [case.case_id for case in cases]
        or not isinstance(hard_gate, int)
        or not all(
            item.get("render_protocol_version")
            == "phase8-runtime-evidence-render-v2"
            and isinstance(item.get("raw_observation_hash"), str)
            and isinstance(item.get("rendered_evidence_hash"), str)
            and isinstance(item.get("oracle_render_hash"), str)
            and item.get("request_utf8_bytes", hard_gate + 1) <= hard_gate
            for item in prompt_records
        )
    ):
        raise ValueError("Phase 8 prompt reproducibility/leakage/size gate failed")
    return {
        "cases": cases,
        "attribution": attribution,
        "fl_records": {item["case_id"]: item for item in fl},
        "partition": partition,
        "prompt_audit": prompt_audit,
        "protocol": protocol,
        "render_protocol": render_protocol,
        "runtime": runtime,
        "status": "passed",
    }


def build_stage1_manifests(
    cases: Sequence[BenchmarkCase], records: Sequence[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_case = {item["case_id"]: item for item in records}
    if len(by_case) != 100 or set(by_case) != {case.case_id for case in cases}:
        raise ValueError("Stage 1 must contain one artifact for all 100 cases")
    entries = []
    eligible = []
    runtime_manifest = json.loads(PHASE8_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    for order, case in enumerate(cases):
        item = by_case[case.case_id]
        if (
            item.get("arm") != "initial"
            or item.get("completed") is not True
            or item.get("protocol_version") != "phase8-v1"
            or item.get("model_parameters", {}).get("provider") != "deepseek"
            or item.get("render_protocol_version")
            != "phase8-runtime-evidence-render-v2"
            or item.get("raw_runtime_manifest_hash")
            != runtime_manifest.get("overall_manifest_hash")
            or item.get("raw_runtime_observation_hash")
            != item.get("prompt", {}).get("raw_observation_hash")
            or item.get("rendered_evidence_hash")
            != item.get("prompt", {}).get("rendered_evidence_hash")
            or item.get("oracle_render_hash")
            != item.get("prompt", {}).get("oracle_render_hash")
        ):
            raise ValueError(f"invalid formal Stage 1 artifact: {case.case_id}")
        entry = {
            "artifact_record_hash": canonical_hash(item),
            "case_id": case.case_id,
            "eligibility_reason": item.get("eligibility_reason"),
            "failure_evidence_hash": item.get("failure_evidence_hash"),
            "first_patch_hash": item.get("first_patch_hash"),
            "initial_prompt_hash": item["prompt"]["hash"],
            "render_protocol_version": item["render_protocol_version"],
            "rendered_evidence_hash": item["prompt"]["rendered_evidence_hash"],
            "raw_runtime_observation_hash": item[
                "raw_runtime_observation_hash"
            ],
            "oracle_render_hash": item["oracle_render_hash"],
            "order": order,
            "second_round_eligible": item.get("second_round_eligible", False),
        }
        entries.append(entry)
        if entry["second_round_eligible"]:
            eligible.append(entry)
    stage1: dict[str, Any] = {
        "artifact_count": len(entries),
        "entries": entries,
        "evaluation_set_sha256": _sha256(PHASE8_EVALUATION_SET),
        "protocol_sha256": _sha256(PHASE8_PROTOCOL),
        "protocol_version": "phase8-stage1-manifest-v1",
        "render_protocol_sha256": _sha256(PHASE8_RENDER_PROTOCOL),
        "test_partition_sha256": _sha256(PHASE8_TEST_PARTITION),
    }
    stage1["overall_manifest_hash"] = canonical_hash(stage1)
    cohort: dict[str, Any] = {
        "eligible_count": len(eligible),
        "entries": eligible,
        "protocol_version": "phase8-eligible-cohort-v1",
        "stage1_manifest_hash": stage1["overall_manifest_hash"],
    }
    cohort["overall_manifest_hash"] = canonical_hash(cohort)
    return stage1, cohort


def _verify_hash_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.get("overall_manifest_hash")
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    if claimed != canonical_hash(unsigned):
        raise ValueError(f"hash mismatch: {path}")
    return value


def validate_stage2_gate() -> dict[str, Any]:
    validate_phase8_preflight()
    if not PHASE8_STAGE1_MANIFEST.is_file() or not PHASE8_ELIGIBLE_COHORT.is_file():
        raise FileNotFoundError("Stage 1 and eligible-cohort manifests are required")
    stage1 = _verify_hash_document(PHASE8_STAGE1_MANIFEST)
    cohort = _verify_hash_document(PHASE8_ELIGIBLE_COHORT)
    if (
        stage1.get("artifact_count") != 100
        or cohort.get("stage1_manifest_hash") != stage1["overall_manifest_hash"]
        or cohort.get("eligible_count") != len(cohort.get("entries", []))
    ):
        raise ValueError("Stage 2 frozen cohort gate mismatch")
    stage1_by_case = {item["case_id"]: item for item in stage1.get("entries", [])}
    if len(stage1_by_case) != 100:
        raise ValueError("Stage 1 manifest must contain 100 unique cases")
    for case_id, entry in stage1_by_case.items():
        paths = list((PHASE8_ARTIFACT_ROOT / "initial" / case_id).glob("*.json"))
        if len(paths) != 1:
            raise ValueError(f"expected one frozen Initial artifact for {case_id}")
        artifact = json.loads(paths[0].read_text(encoding="utf-8"))
        if (
            canonical_hash(artifact) != entry.get("artifact_record_hash")
            or artifact.get("first_patch_hash") != entry.get("first_patch_hash")
            or artifact.get("failure_evidence_hash")
            != entry.get("failure_evidence_hash")
            or artifact.get("prompt", {}).get("hash")
            != entry.get("initial_prompt_hash")
            or artifact.get("render_protocol_version")
            != entry.get("render_protocol_version")
            or artifact.get("prompt", {}).get("rendered_evidence_hash")
            != entry.get("rendered_evidence_hash")
            or artifact.get("raw_runtime_observation_hash")
            != entry.get("raw_runtime_observation_hash")
            or artifact.get("oracle_render_hash")
            != entry.get("oracle_render_hash")
        ):
            raise ValueError(f"Stage 1 artifact binding mismatch for {case_id}")
    for entry in cohort["entries"]:
        if (
            not entry.get("second_round_eligible")
            or not entry.get("first_patch_hash")
            or not entry.get("failure_evidence_hash")
            or stage1_by_case.get(entry.get("case_id")) != entry
        ):
            raise ValueError("Stage 2 cohort entry lacks frozen patch/evidence")
    return {"cohort": cohort, "stage1": stage1, "status": "passed"}
