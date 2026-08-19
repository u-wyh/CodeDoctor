"""Render and leakage-audit all 100 Phase 8 Initial prompts offline."""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE8_EVALUATION_SET,
    PHASE8_FL,
    PHASE8_PROMPT_AUDIT,
    PHASE8_TEST_PARTITION,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.deepseek import DeepSeekProvider, model_parameters  # noqa: E402
from repair_phase8.context import build_initial_context  # noqa: E402
from repair_phase8.partition import canonical_hash, load_partition_manifest  # noqa: E402
from repair_phase8.prompting import render_initial_prompt  # noqa: E402
from repair_phase8.runtime_evidence import load_phase8_runtime  # noqa: E402


CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")


def _read_fl() -> dict[str, dict[str, object]]:
    return {
        item["case_id"]: item
        for item in (
            json.loads(line)
            for line in PHASE8_FL.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def render_all() -> tuple[list[dict[str, str]], dict[str, str]]:
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    runtime = load_phase8_runtime(cases)
    fl = _read_fl()
    provider = DeepSeekProvider(
        model_parameters(120.0), "offline-placeholder", "DEEPSEEK_API_KEY"
    )
    records = []
    payloads = {}
    for case in cases:
        context = build_initial_context(case, fl[case.case_id], runtime.evaluations[case.case_id])
        prompt = render_initial_prompt(
            context, set(case.metadata["phase8"]["base_test_ids"])
        )
        serialized = json.dumps(
            provider.request_payload(prompt),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        records.append(
            {
                "case_id": case.case_id,
                "payload_hash": hashlib.sha256(serialized.encode()).hexdigest(),
                "prompt_hash": prompt.prompt_hash,
            }
        )
        payloads[case.case_id] = serialized
    return records, payloads


def main() -> int:
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    if len(cases) != 100:
        raise ValueError("Phase 8 prompt audit requires 100 cases")
    first, payloads = render_all()
    second, _ = render_all()
    if first != second:
        raise ValueError("Phase 8 Initial prompt hashes changed across reloads")
    serialized = "\n".join(payloads.values())
    violations = []
    if any(canary in serialized for canary in CANARIES):
        violations.append("evaluation canary")
    if re.search(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}", serialized):
        violations.append("credential-like value")
    for case in cases:
        reference = case.get_reference_source(evaluation_only=True)
        if reference and reference in payloads[case.case_id]:
            violations.append(f"{case.case_id}: reference source")
        public_ids = set(case.metadata["phase8"]["base_test_ids"]) | set(
            case.metadata["phase8"]["feedback_test_ids"]
        )
        if public_ids != {item.test_id for item in case.tests.repair_tests}:
            violations.append(f"{case.case_id}: public oracle mismatch")
    if violations:
        raise ValueError(f"Phase 8 Initial prompt leakage: {violations}")
    partition = load_partition_manifest(PHASE8_TEST_PARTITION)
    runtime = load_phase8_runtime(cases)
    maximum_bytes = 400_000
    payload_sizes = {
        case_id: len(payload.encode("utf-8")) for case_id, payload in payloads.items()
    }
    oversized = [
        {"case_id": case_id, "request_utf8_bytes": size}
        for case_id, size in sorted(
            payload_sizes.items(), key=lambda item: (-item[1], item[0])
        )
        if size > maximum_bytes
    ]
    value = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hashes_identical_across_reloads": True,
        "leakage_audit": {
            "credential_absent": "passed",
            "evaluation_canaries_absent": "passed",
            "hidden_validation_absent": "passed",
            "reference_source_absent": "passed",
            "status": "passed",
        },
        "partition_manifest_hash": partition["overall_manifest_hash"],
        "operational_size_gate": {
            "maximum_initial_request_utf8_bytes": maximum_bytes,
            "maximum_observed_request_utf8_bytes": max(payload_sizes.values()),
            "oversized_count": len(oversized),
            "oversized_requests": oversized,
            "status": "failed" if oversized else "passed",
        },
        "prompt_records": first,
        "prompt_set_hash": canonical_hash(first),
        "prompts_checked": len(first),
        "protocol_version": "phase8-initial-prompt-audit-v1",
        "runtime_manifest_hash": runtime.validation["manifest_hash"],
    }
    PHASE8_PROMPT_AUDIT.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {PHASE8_PROMPT_AUDIT}; prompts={len(first)}; "
        f"prompt_set_hash={value['prompt_set_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
