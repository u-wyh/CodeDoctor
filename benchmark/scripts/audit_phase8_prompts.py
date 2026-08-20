"""Freeze Phase 8 v2 Initial prompts with size, leakage, and stability audits."""

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE8_EVALUATION_SET,
    PHASE8_FL,
    PHASE8_PAYLOAD_ATTRIBUTION,
    PHASE8_PROMPT_AUDIT,
    PHASE8_RENDER_PROTOCOL,
    PHASE8_TEST_PARTITION,
    PROJECT_ROOT,
)
from benchmark.models import BenchmarkCase, load_manifest  # noqa: E402
from repair.deepseek import DeepSeekProvider, model_parameters  # noqa: E402
from repair_phase8.context import build_initial_context  # noqa: E402
from repair_phase8.evidence_rendering import RENDER_PROTOCOL_VERSION  # noqa: E402
from repair_phase8.partition import canonical_hash, load_partition_manifest  # noqa: E402
from repair_phase8.prompting import render_initial_prompt  # noqa: E402
from repair_phase8.runtime_evidence import load_phase8_runtime  # noqa: E402


CANARIES = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")
CREDENTIAL_PATTERN = re.compile(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}")
REASONING_PATTERN = re.compile(r'"reasoning_content"\s*:\s*"')
RANDOM_ORDER_SEED = 20260820


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_fl() -> dict[str, dict[str, object]]:
    return {
        item["case_id"]: item
        for item in (
            json.loads(line)
            for line in PHASE8_FL.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def _provider() -> DeepSeekProvider:
    return DeepSeekProvider(
        model_parameters(120.0), "offline-placeholder", "DEEPSEEK_API_KEY"
    )


def _render_case(
    case: BenchmarkCase,
    fl: dict[str, dict[str, object]],
    runtime: object,
    provider: DeepSeekProvider,
) -> tuple[dict[str, object], str]:
    context = build_initial_context(
        case, fl[case.case_id], runtime.evaluations[case.case_id]
    )
    prompt = render_initial_prompt(
        context, set(case.metadata["phase8"]["base_test_ids"])
    )
    serialized = json.dumps(
        provider.request_payload(prompt),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    payload_bytes = len(serialized.encode("utf-8"))
    return (
        {
            "case_id": case.case_id,
            "estimated_input_tokens": math.ceil(payload_bytes / 4),
            "oracle_render_hash": prompt.oracle_render_hash,
            "payload_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "prompt_hash": prompt.prompt_hash,
            "raw_observation_hash": prompt.raw_observation_hash,
            "render_protocol_version": prompt.render_protocol_version,
            "rendered_evidence_hash": prompt.rendered_evidence_hash,
            "request_utf8_bytes": payload_bytes,
        },
        serialized,
    )


def render_all(
    render_order: list[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    canonical_cases = list(load_manifest(PHASE8_EVALUATION_SET))
    runtime = load_phase8_runtime(canonical_cases)
    by_id = {case.case_id: case for case in canonical_cases}
    order = render_order or [case.case_id for case in canonical_cases]
    if set(order) != set(by_id) or len(order) != len(by_id):
        raise ValueError("render order must contain every Phase 8 case exactly once")
    fl = _read_fl()
    provider = _provider()
    rendered = {
        case_id: _render_case(by_id[case_id], fl, runtime, provider)
        for case_id in order
    }
    records = [rendered[case.case_id][0] for case in canonical_cases]
    payloads = {case.case_id: rendered[case.case_id][1] for case in canonical_cases}
    return records, payloads


def _stats(values: list[int]) -> dict[str, int | float]:
    ordered = sorted(values)
    return {
        "max": max(ordered),
        "mean": round(statistics.fmean(ordered), 3),
        "median": statistics.median(ordered),
        "min": min(ordered),
        "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "total": sum(ordered),
    }


def _stress_oversized(
    cases: list[BenchmarkCase], attribution: dict[str, object]
) -> list[dict[str, object]]:
    runtime = load_phase8_runtime(cases)
    fl = _read_fl()
    provider = _provider()
    by_id = {case.case_id: case for case in cases}
    results = []
    for old in attribution["oversized_cases"]:
        case_id = old["case_id"]
        hashes = []
        sizes = []
        for _ in range(10):
            record, _ = _render_case(by_id[case_id], fl, runtime, provider)
            hashes.append(record["prompt_hash"])
            sizes.append(record["request_utf8_bytes"])
        results.append(
            {
                "after_request_utf8_bytes": sizes[0],
                "before_request_utf8_bytes": old["total_payload_bytes"],
                "case_id": case_id,
                "hashes_identical_10_of_10": len(set(hashes)) == 1,
                "reduction_ratio": round(sizes[0] / old["total_payload_bytes"], 8),
            }
        )
    return results


def _leakage_audit(
    cases: list[BenchmarkCase], payloads: dict[str, str]
) -> dict[str, object]:
    violations = []
    combined = "\n".join(payloads.values())
    if any(canary in combined for canary in CANARIES):
        violations.append("evaluation canary in rendered/provider payload")
    if CREDENTIAL_PATTERN.search(combined):
        violations.append("credential-like value in rendered/provider payload")
    if REASONING_PATTERN.search(combined):
        violations.append("raw reasoning in rendered/provider payload")
    runtime_manifest = load_phase8_runtime(cases).manifest
    raw_documents = {}
    for entry in runtime_manifest["artifacts"]:
        path = PROJECT_ROOT / entry["path"]
        raw_documents[entry["case_id"]] = path.read_text(
            encoding="utf-8", errors="replace"
        )
    raw_combined = "\n".join(raw_documents.values())
    if any(canary in raw_combined for canary in CANARIES):
        violations.append("evaluation canary in raw snapshot")
    if CREDENTIAL_PATTERN.search(raw_combined):
        violations.append("credential-like value in raw snapshot")
    if REASONING_PATTERN.search(raw_combined):
        violations.append("raw reasoning in raw snapshot")
    for case in cases:
        payload = payloads[case.case_id]
        raw = raw_documents[case.case_id]
        reference = case.get_reference_source(evaluation_only=True)
        if reference and (reference in payload or reference in raw):
            violations.append(f"{case.case_id}: reference source")
        hidden_ids = set(case.metadata["phase8"]["hidden_test_ids"])
        if any(test_id in payload or test_id in raw for test_id in hidden_ids):
            violations.append(f"{case.case_id}: hidden validation id")
        public_ids = set(case.metadata["phase8"]["base_test_ids"]) | set(
            case.metadata["phase8"]["feedback_test_ids"]
        )
        if public_ids != {item.test_id for item in case.tests.repair_tests}:
            violations.append(f"{case.case_id}: public oracle mismatch")
    if violations:
        raise ValueError(f"Phase 8 prompt leakage: {violations}")
    return {
        "credential_absent": "passed",
        "evaluation_canaries_absent": "passed",
        "hidden_validation_absent": "passed",
        "raw_reasoning_absent": "passed",
        "raw_snapshots_checked": len(raw_documents),
        "reference_source_absent": "passed",
        "rendered_and_provider_payloads_checked": len(payloads),
        "status": "passed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    if len(cases) != 100:
        raise ValueError("Phase 8 prompt audit requires 100 cases")
    first, payloads = render_all()
    second, _ = render_all()
    random_order = [case.case_id for case in cases]
    random.Random(RANDOM_ORDER_SEED).shuffle(random_order)
    randomized, _ = render_all(random_order)
    if first != second or first != randomized:
        raise ValueError("Phase 8 Initial prompt hashes changed across reload/order")
    attribution = json.loads(PHASE8_PAYLOAD_ATTRIBUTION.read_text(encoding="utf-8"))
    stress = _stress_oversized(cases, attribution)
    if not all(item["hashes_identical_10_of_10"] for item in stress):
        raise ValueError("oversized-case repeated rendering is unstable")
    leakage = _leakage_audit(cases, payloads)
    partition = load_partition_manifest(PHASE8_TEST_PARTITION)
    runtime = load_phase8_runtime(cases)
    render_protocol = json.loads(PHASE8_RENDER_PROTOCOL.read_text(encoding="utf-8"))
    if render_protocol.get("protocol_version") != RENDER_PROTOCOL_VERSION:
        raise ValueError("Phase 8 rendering protocol mismatch")
    sizes = [int(item["request_utf8_bytes"]) for item in first]
    tokens = [int(item["estimated_input_tokens"]) for item in first]
    hard_gate = int(render_protocol["hard_serialized_payload_bytes"])
    warning = int(render_protocol["warning_serialized_payload_bytes"])
    oversized = [item for item in first if item["request_utf8_bytes"] > hard_gate]
    top = sorted(first, key=lambda item: (-item["request_utf8_bytes"], item["case_id"]))[:10]
    value = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hashes_identical_across_reloads": True,
        "leakage_audit": leakage,
        "operational_size_gate": {
            "maximum_initial_request_utf8_bytes": hard_gate,
            "maximum_observed_request_utf8_bytes": max(sizes),
            "oversized_count": len(oversized),
            "oversized_requests": oversized,
            "status": "failed" if oversized else "passed",
            "warning_count": sum(size > warning for size in sizes),
            "warning_threshold_utf8_bytes": warning,
        },
        "oversized_case_stress": stress,
        "partition_manifest_hash": partition["overall_manifest_hash"],
        "payload_byte_statistics": _stats(sizes),
        "prompt_records": first,
        "prompt_set_hash": canonical_hash(first),
        "prompts_checked": len(first),
        "protocol_version": "phase8-initial-prompt-audit-v2",
        "render_protocol": {
            "path": str(PHASE8_RENDER_PROTOCOL.relative_to(PROJECT_ROOT)),
            "protocol_version": RENDER_PROTOCOL_VERSION,
            "sha256": _sha256(PHASE8_RENDER_PROTOCOL),
        },
        "reproducibility": {
            "manifest_order_reload_equal": True,
            "random_order_reload_equal": True,
            "random_order_seed": RANDOM_ORDER_SEED,
        },
        "runtime_manifest_hash": runtime.validation["manifest_hash"],
        "superseded_prompt_set_hash": attribution["superseded_prompt_set_hash"],
        "token_estimate_method": "ceil(serialized UTF-8 bytes / 4)",
        "estimated_input_token_statistics": _stats(tokens),
        "top_10_largest_requests": top,
    }
    PHASE8_PROMPT_AUDIT.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {PHASE8_PROMPT_AUDIT}; prompts={len(first)}; "
        f"max_bytes={max(sizes)}; prompt_set_hash={value['prompt_set_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
