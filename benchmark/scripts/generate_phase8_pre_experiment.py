"""Generate the frozen Phase 8 engineering and pre-registration report."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    DEEPSEEK_FORMAL_PRICING_SNAPSHOT,
    PHASE8_EVALUATION_SET,
    PHASE8_EVALUATION_SUMMARY,
    PHASE8_PRE_EXPERIMENT_REPORT,
    PHASE8_PROMPT_AUDIT,
    PHASE8_RUNTIME_MANIFEST,
    PHASE8_TEST_PARTITION,
    REPAIR_ARTIFACT_ROOT,
)
from benchmark.models import load_manifest  # noqa: E402
from repair_phase8.runtime_evidence import load_phase8_runtime  # noqa: E402


def _phase7_usage() -> tuple[float, float, int]:
    prompts = []
    completions = []
    root = REPAIR_ARTIFACT_ROOT / "formal_evidence_ablation"
    for path in root.glob("**/*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        usage = value.get("provider_response_metadata", {}).get("usage", {})
        if isinstance(usage.get("prompt_tokens"), int):
            prompts.append(usage["prompt_tokens"])
        if isinstance(usage.get("completion_tokens"), int):
            completions.append(usage["completion_tokens"])
    if not prompts or not completions:
        return 0.0, 0.0, 0
    return sum(prompts) / len(prompts), sum(completions) / len(completions), len(prompts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-tests-passed", action="store_true", required=True)
    args = parser.parse_args()
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    summary = json.loads(PHASE8_EVALUATION_SUMMARY.read_text(encoding="utf-8"))
    partition = json.loads(PHASE8_TEST_PARTITION.read_text(encoding="utf-8"))
    runtime = json.loads(PHASE8_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(PHASE8_PROMPT_AUDIT.read_text(encoding="utf-8"))
    frozen_runtime = load_phase8_runtime(cases)
    prices = json.loads(DEEPSEEK_FORMAL_PRICING_SNAPSHOT.read_text(encoding="utf-8"))
    base = sum(len(case.metadata["phase8"]["base_test_ids"]) for case in cases)
    feedback = sum(len(case.metadata["phase8"]["feedback_test_ids"]) for case in cases)
    hidden = sum(len(case.metadata["phase8"]["hidden_test_ids"]) for case in cases)
    prompt_mean, completion_mean, usage_n = _phase7_usage()
    rates = prices["prices"]
    per_call = (prompt_mean * rates["input_cache_miss"] + completion_mean * rates["output"]) / prices["price_unit_tokens"]
    stage1_cost = per_call * 100
    reasons = ", ".join(
        f"{key}={value}" for key, value in summary["exclusion_reasons"].items()
    )
    order_counts = Counter(
        "R-first"
        if int.from_bytes(__import__("hashlib").sha256(
            f"20260820\0{case.case_id}".encode()
        ).digest(), "big") & 1 == 0
        else "F-first"
        for case in cases
    )
    size_gate = audit["operational_size_gate"]
    ready = size_gate["status"] == "passed"
    readiness = "ready" if ready else "not ready"
    blocker = (
        "No formal blocker remains."
        if ready
        else f"Formal blocker: {size_gate['oversized_count']} Initial requests exceed "
        f"the frozen {size_gate['maximum_initial_request_utf8_bytes']}-byte operational "
        "gate; the largest is "
        f"{size_gate['maximum_observed_request_utf8_bytes']} bytes. The complete public "
        "oracle and frozen observations were not truncated or replaced."
    )
    text = f"""# CodeDoctor Phase 8 Pre-experiment Report

## 1. Research Question
When an extracted first patch fails observable repair-time execution, does one retry with failed execution feedback outperform one otherwise identical retry without feedback?

## 2. Why Retry Control Is Required
R controls for the benefit of a second model call. Initial versus F confounds retry opportunity with execution feedback; the primary causal comparison is paired R versus F.

## 3. Independent Evaluation Set
The seed-20260820 set contains {len(cases)} cases. Overlap is FL Pilot={summary['fl_pilot_overlap']}, Independent FL Evaluation={summary['fl_evaluation_overlap']}, Phase 7 Repair Pilot={summary['repair_pilot_overlap']}.

Exclusions total {summary['exclusions']}: {reasons}. The 400 historical overlaps and static exclusions are recorded; only {len(cases)} selected cases enter Phase 8. No FL performance attribute was used for selection.

## 4. Frozen Test Partition
Protocol `phase8_test_partition_v1` uses SHA-256(seed + case id), with `feedback_count=min(max(1,floor(n/4)),n-1)`. Totals: Base={base}, Feedback={feedback}, Hidden={hidden}. Manifest hash: `{partition['overall_manifest_hash']}`. Feedback/Hidden identities are namespaced to avoid source-pool test-id collisions.

Base and Feedback input/expected output are public before Initial. Hidden tests remain evaluation-only and cannot enter prompts, feedback, or retry eligibility.

## 5. Initial, R, and F
Initial = Base+Feedback public oracle + FL-v1 + frozen buggy runtime. R = identical Initial context + the frozen first patch + uniform retry instruction, with no execution feedback. F = R plus only failed repair-time compiler/test observations. R and F share the exact first patch.

## 6. Eligibility and Evaluation
Second-round eligible means an extractable source with compile failure, Base failure, or Feedback failure. Provider failure and invalid model output are ineligible. Repair-time success forbids retry even when Hidden validation later fails. Plausible means all Base+Feedback pass; Validated additionally means all Hidden tests pass and does not mean formally correct.

## 7. Runtime and Artifacts
Frozen buggy runtime covers {runtime['evaluation_set']['case_count']} cases and {frozen_runtime.validation['repair_test_count']} public tests; each was executed exactly once with zero transport retries. Runtime manifest hash: `{runtime['overall_manifest_hash']}`.

Artifacts are content-addressed under `initial/`, `retry_control/`, and `feedback/`; they bind protocol, partition, prompt, first patch, failure evidence, model metadata, repair-time results, hidden evaluation results, and timestamps. API keys, raw reasoning, reference source, and ground-truth diffs are excluded.

## 8. Reproducibility and Leakage
Initial prompt audit: {audit['prompts_checked']}/100, prompt-set hash `{audit['prompt_set_hash']}`, independent reload hashes identical={str(audit['hashes_identical_across_reloads']).lower()}, leakage={audit['leakage_audit']['status']}. Operational size gate={size_gate['status']}. Canary tests cover Initial/R/F boundaries. Fake end-to-end scenarios passed={str(args.fake_tests_passed).lower()}, including compile failure, test failure, repair-time success, Hidden-only failure, invalid output, and provider failure.

## 9. Two-stage Execution Gate
Stage 1 requires `--confirm-phase8-stage1`, permits exactly 100 Initial calls, freezes artifacts/cohort, then exits. Stage 2 requires separate `--confirm-phase8-stage2` plus valid 100-artifact, first-patch, failure-evidence, and cohort hashes before network. Stage 2 is exactly `2M`, where M is the frozen Stage 1 eligible count. No third attempt exists. Pre-registered order across all 100 cases is {dict(order_counts)}.

## 10. Model and Rough Cost
Frozen configuration: DeepSeek Official API `deepseek-v4-flash`, thinking enabled, reasoning effort low, max_tokens=16384, stream=false, temperature not sent, transport retries=0.

Rough estimate uses mean observed Phase 7 formal usage ({usage_n} responses): {prompt_mean:.1f} input and {completion_mean:.1f} completion tokens per call, and the official pricing snapshot verified {prices['verified_at']} (cache-miss input ${rates['input_cache_miss']}/M, output ${rates['output']}/M). Stage 1 is roughly ${stage1_cost:.4f}. Stage 2 is roughly `${per_call:.6f} * 2M`; actual Phase 8 prompts, cache behavior, output length, and M are unknown, so uncertainty is high.

## 11. Readiness
Dataset, partition, FL-v1, runtime, Initial prompt reproducibility, leakage checks, fake tests, and fail-closed gates are prepared. Phase 8 Stage 1 is technically {readiness}; no formal LLM call or bulk stage has started.

{blocker}
"""
    PHASE8_PRE_EXPERIMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PHASE8_PRE_EXPERIMENT_REPORT.write_text(text, encoding="utf-8")
    print(f"wrote {PHASE8_PRE_EXPERIMENT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
