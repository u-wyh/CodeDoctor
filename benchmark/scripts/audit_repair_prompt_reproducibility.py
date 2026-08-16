"""Render formal prompts from frozen evidence twice without calling an LLM."""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    REPAIR_PILOT_FL,
    RUNTIME_EVIDENCE_MANIFEST,
    RUNTIME_EVIDENCE_PROMPT_AUDIT,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.context import build_repair_context, load_fl_records  # noqa: E402
from repair.deepseek import DeepSeekProvider, model_parameters  # noqa: E402
from repair.models import EvidenceGroup, PromptDocument  # noqa: E402
from repair.pre_experiment import _validate_prompts  # noqa: E402
from repair.prompting import render_prompt  # noqa: E402
from repair.protocol import validate_repair_protocol  # noqa: E402
from repair.runtime_evidence import load_frozen_runtime_evidence  # noqa: E402


TARGET_CASE = "450-B-bug-15950152-15950193"
FORBIDDEN_KEYS = {
    "api_key",
    "credential",
    "ground_truth",
    "ground_truth_diff",
    "hidden_validation",
    "reference",
    "reference_source",
    "validation_tests",
}
CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _forbidden_key_paths(value: object, prefix: str = "") -> list[str]:
    violations = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_KEYS:
                violations.append(path)
            violations.extend(_forbidden_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(_forbidden_key_paths(item, f"{prefix}[{index}]"))
    return violations


def _render_all() -> tuple[
    list[dict[str, str]],
    dict[str, dict[str, PromptDocument]],
    dict[str, str],
]:
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    frozen = load_frozen_runtime_evidence(cases)
    fl_records = load_fl_records(REPAIR_PILOT_FL)
    provider = DeepSeekProvider(
        model_parameters(120.0), "offline-placeholder", "DEEPSEEK_API_KEY"
    )
    records = []
    prompts = {}
    payloads = {}
    for case in cases:
        case_prompts = {}
        for group in EvidenceGroup:
            context = build_repair_context(
                case,
                group,
                fl_records.get(case.case_id),
                frozen.evaluations[case.case_id],
            )
            prompt = render_prompt(context, group)
            payload = provider.request_payload(prompt)
            serialized = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            records.append(
                {
                    "case_id": case.case_id,
                    "group": group.value,
                    "payload_hash": hashlib.sha256(serialized.encode()).hexdigest(),
                    "prompt_hash": prompt.prompt_hash,
                }
            )
            case_prompts[group.value] = prompt
            payloads[f"{case.case_id}/{group.value}"] = serialized
        prompts[case.case_id] = case_prompts
    return records, prompts, payloads


def main() -> int:
    validate_repair_protocol()
    first, first_prompts, payloads = _render_all()
    second, second_prompts, _ = _render_all()
    if first != second:
        raise ValueError("formal prompt hashes changed across independent snapshot reloads")
    first_audit = _validate_prompts(first_prompts)
    second_audit = _validate_prompts(second_prompts)
    if first_audit["prompts_checked"] != 150 or second_audit["prompts_checked"] != 150:
        raise ValueError("formal prompt audit did not render 150 prompts")
    target_hashes = []
    for _ in range(10):
        records, _, _ = _render_all()
        target_hashes.append(
            next(
                item["prompt_hash"]
                for item in records
                if item["case_id"] == TARGET_CASE and item["group"] == "C"
            )
        )
    if len(set(target_hashes)) != 1:
        raise ValueError("450-B Group C prompt changed across frozen-evidence reloads")

    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    manifest = json.loads(RUNTIME_EVIDENCE_MANIFEST.read_text(encoding="utf-8"))
    violations = _forbidden_key_paths(manifest)
    snapshot_documents = []
    for entry in manifest["artifacts"]:
        path = Path(__file__).resolve().parents[2] / entry["path"]
        document = json.loads(path.read_text(encoding="utf-8"))
        snapshot_documents.append(document)
        violations.extend(_forbidden_key_paths(document, entry["case_id"]))
    serialized_all = "\n".join(payloads.values())
    serialized_snapshots = json.dumps(
        [manifest, *snapshot_documents], ensure_ascii=False, sort_keys=True
    )
    if any(
        canary in value
        for canary in CANARIES
        for value in (serialized_all, serialized_snapshots)
    ):
        violations.append("evaluation canary in runtime evidence or provider payload")
    for case in cases:
        reference = case.get_reference_source(evaluation_only=True)
        for group in EvidenceGroup:
            if reference and reference in payloads[f"{case.case_id}/{group.value}"]:
                violations.append(f"{case.case_id}/{group.value}: reference source")
    if re.search(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}", serialized_all):
        violations.append("credential-like value in serialized provider payload")
    if re.search(
        r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}", serialized_snapshots
    ):
        violations.append("credential-like value in frozen runtime evidence")
    if violations:
        raise ValueError(f"runtime evidence leakage audit failed: {violations}")

    value = {
        "all_prompt_hashes_identical_across_reloads": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leakage_audit": {
            "credential_absent": "passed",
            "evaluation_canaries_absent": "passed",
            "forbidden_snapshot_keys_absent": "passed",
            "hidden_validation_absent": "passed",
            "reference_source_absent": "passed",
            "status": "passed",
        },
        "payloads_checked": len(payloads),
        "prompt_records": first,
        "prompt_set_hash": _canonical_hash(first),
        "prompts_checked": len(first),
        "protocol_version": "runtime-evidence-prompt-audit-v1",
        "runtime_evidence_manifest_hash": manifest["overall_manifest_hash"],
        "target_case_c_hashes": target_hashes,
        "target_case_c_ten_render_hashes_identical": True,
        "target_case_id": TARGET_CASE,
    }
    RUNTIME_EVIDENCE_PROMPT_AUDIT.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {RUNTIME_EVIDENCE_PROMPT_AUDIT}; prompts={len(first)}; "
        f"prompt_set_hash={value['prompt_set_hash']}; target_reloads=10"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
