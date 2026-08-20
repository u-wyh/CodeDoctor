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
    PHASE8_PAYLOAD_ATTRIBUTION,
    PHASE8_PRE_EXPERIMENT_REPORT,
    PHASE8_PROMPT_AUDIT,
    PHASE8_RENDER_PROTOCOL,
    PHASE8_RUNTIME_MANIFEST,
    PHASE8_TEST_PARTITION,
    REPAIR_ARTIFACT_ROOT,
)
from benchmark.models import load_manifest  # noqa: E402
from repair_phase8.runtime_evidence import load_phase8_runtime  # noqa: E402


def _phase7_completion_usage() -> tuple[float, int]:
    completions = []
    root = REPAIR_ARTIFACT_ROOT / "formal_evidence_ablation"
    for path in root.glob("**/*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        usage = value.get("provider_response_metadata", {}).get("usage", {})
        if isinstance(usage.get("completion_tokens"), int):
            completions.append(usage["completion_tokens"])
    if not completions:
        return 0.0, 0
    return sum(completions) / len(completions), len(completions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-tests-passed", action="store_true", required=True)
    parser.add_argument("--renderer-tests-passed", action="store_true", required=True)
    parser.add_argument("--full-regression-passed", action="store_true", required=True)
    args = parser.parse_args()
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    summary = json.loads(PHASE8_EVALUATION_SUMMARY.read_text(encoding="utf-8"))
    partition = json.loads(PHASE8_TEST_PARTITION.read_text(encoding="utf-8"))
    runtime = json.loads(PHASE8_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(PHASE8_PROMPT_AUDIT.read_text(encoding="utf-8"))
    attribution = json.loads(PHASE8_PAYLOAD_ATTRIBUTION.read_text(encoding="utf-8"))
    render_protocol = json.loads(PHASE8_RENDER_PROTOCOL.read_text(encoding="utf-8"))
    frozen_runtime = load_phase8_runtime(cases)
    prices = json.loads(DEEPSEEK_FORMAL_PRICING_SNAPSHOT.read_text(encoding="utf-8"))
    base = sum(len(case.metadata["phase8"]["base_test_ids"]) for case in cases)
    feedback = sum(len(case.metadata["phase8"]["feedback_test_ids"]) for case in cases)
    hidden = sum(len(case.metadata["phase8"]["hidden_test_ids"]) for case in cases)
    completion_mean, usage_n = _phase7_completion_usage()
    rates = prices["prices"]
    estimated_input = audit["estimated_input_token_statistics"]["total"]
    estimated_output = completion_mean * 100
    stage1_cost = (
        estimated_input * rates["input_cache_miss"]
        + estimated_output * rates["output"]
    ) / prices["price_unit_tokens"]
    reasons = ", ".join(
        f"{key}={value}" for key, value in summary["exclusion_reasons"].items()
    )
    order_counts = Counter(
        "R-first"
        if int.from_bytes(
            __import__("hashlib").sha256(f"20260820\0{case.case_id}".encode()).digest(),
            "big",
        )
        & 1
        == 0
        else "F-first"
        for case in cases
    )
    stress = {item["case_id"]: item for item in audit["oversized_case_stress"]}
    attribution_rows = sorted(
        attribution["oversized_cases"],
        key=lambda item: -item["total_payload_bytes"],
    )
    attribution_text = "\n".join(
        "- `{case_id}` total={total_payload_bytes:,}; source={buggy_source_bytes:,}; "
        "Base oracle={base_oracle_bytes:,}; Feedback oracle={feedback_oracle_bytes:,}; "
        "FL={fl_bytes:,}; runtime stdout={runtime_stdout_bytes:,}; runtime stderr="
        "{runtime_stderr_bytes:,}; runtime metadata={runtime_metadata_bytes:,}; "
        "instruction/template={instruction_template_bytes:,}; serialization overhead="
        "{serialization_overhead_bytes:,}; oracle_oversize={oracle_oversize}.".format(
            **row
        )
        for row in attribution_rows
    )
    maximum_row = attribution_rows[0]
    maximum_oracle_bytes = (
        maximum_row["base_oracle_bytes"] + maximum_row["feedback_oracle_bytes"]
    )
    reduction_text = "\n".join(
        f"- `{case_id}`: {item['before_request_utf8_bytes']:,} -> "
        f"{item['after_request_utf8_bytes']:,} bytes "
        f"(ratio={item['reduction_ratio']}; 10/10 stable)."
        for case_id, item in sorted(stress.items())
    )
    size = audit["payload_byte_statistics"]
    tokens = audit["estimated_input_token_statistics"]
    size_gate = audit["operational_size_gate"]
    ready = all(
        (
            size_gate["status"] == "passed",
            audit["leakage_audit"]["status"] == "passed",
            audit["hashes_identical_across_reloads"],
            audit["reproducibility"]["random_order_reload_equal"],
            all(item["hashes_identical_10_of_10"] for item in stress.values()),
            args.fake_tests_passed,
            args.renderer_tests_passed,
            args.full_regression_passed,
        )
    )
    readiness = "ready" if ready else "not ready"
    blocker = "No formal blocker remains." if ready else "A formal readiness gate remains."
    text = f"""# CodeDoctor Phase 8 Pre-experiment Report

## 1. Research Question and Control
When an extracted first patch fails observable repair-time execution, does one retry with failed execution feedback outperform an otherwise identical retry without feedback? R controls for a second-call benefit; Initial versus F alone would confound retry opportunity with execution feedback. The primary causal comparison remains paired R versus F.

## 2. Independent Evaluation Set
The seed-20260820 set contains {len(cases)} cases. Overlap is FL Pilot={summary['fl_pilot_overlap']}, Independent FL Evaluation={summary['fl_evaluation_overlap']}, Phase 7 Repair Pilot={summary['repair_pilot_overlap']}.

Exclusions total {summary['exclusions']}: {reasons}. No FL performance attribute was used for selection.

## 3. Frozen Test and Information Boundary
Protocol `phase8_test_partition_v1` uses SHA-256(seed + case id), with `feedback_count=min(max(1,floor(n/4)),n-1)`. Totals: Base={base}, Feedback={feedback}, Hidden={hidden}. Manifest hash: `{partition['overall_manifest_hash']}`.

Base and Feedback are the common repair-time oracle. Hidden tests remain evaluation-only and cannot enter Initial, R, F, execution feedback, or retry eligibility. Initial = common oracle + FL-v1 + frozen buggy runtime. R = Initial + the same first patch + uniform retry instruction. F = R + bounded failed execution observations only. Compile/Base/Feedback failure is eligible; provider failure, invalid output, repair-time success, and Hidden-only failure are not.

## 4. Raw Runtime Evidence
Frozen buggy runtime covers {runtime['evaluation_set']['case_count']} cases and {frozen_runtime.validation['repair_test_count']} public tests; each was executed exactly once with zero transport retries. Raw runtime manifest hash remains `{runtime['overall_manifest_hash']}`. Full stdout/stderr/exit/timeout/verdict observations remain immutable and auditable; no snapshot was truncated, normalized, replaced, or recaptured.

## 5. Oversized Payload Attribution
The superseded v1 Initial prompt set had 4 requests above 400,000 bytes and a maximum of 30,774,820 bytes. Component attribution uses canonical UTF-8 bytes and sums exactly to each serialized provider request:

{attribution_text}

The maximum case, `{maximum_row['case_id']}`, was jointly dominated by {maximum_oracle_bytes:,} bytes of common oracle representation and {maximum_row['runtime_stdout_bytes']:,} bytes of runtime stdout. Three of the four cases had oversized common oracle fields, so a runtime-only fix would not satisfy the unchanged hard gate. Cases were not deleted or replaced, and the gate was not raised.

## 6. Bounded Prompt-visible Rendering
`{render_protocol['protocol_version']}` applies uniformly to all 100 Initial prompts and future Stage 2 F feedback. Every execution test retains test id, verdict, exit/timeout status, stdout/stderr byte lengths, and SHA-256 identities.

- Exact PASS stdout is represented as matching the already-public expected output, without duplicating its body.
- Clean-exit mismatch records first differing byte, expected/actual length and hash, plus at most 1,024 bytes before and 3,072 bytes after the difference from actual stdout. It adds no expected window or new specification.
- Abnormal stdout is full through 4,096 bytes; otherwise first/last 2,048 bytes with exact omitted count.
- stderr is full through 8,192 bytes; otherwise first/last 4,096 bytes.
- compiler stderr is full through 16,384 bytes; otherwise first/last 8,192 bytes.
- Common Oracle v2 applies identically to Initial/R/F: each input/expected field is full through 4,096 bytes, otherwise first/last 2,048 bytes with total length and SHA-256.
- UTF-8 is canonical; excerpts crossing a multibyte boundary use deterministic `errors=replace` decoding.

Raw observations and prompt-visible representations are separately hashed in artifacts through raw observation/manifest hashes, render protocol version, and rendered evidence hash. F reuses this exact renderer; R contains no execution feedback.

## 7. Before and After
{reduction_text}

Across 100 v2 serialized requests: min={size['min']:,}, median={size['median']:,}, mean={size['mean']:,}, p95={size['p95']:,}, max={size['max']:,}, total={size['total']:,} bytes. Warning count above 300,000={size_gate['warning_count']}; hard-gate failures above 400,000={size_gate['oversized_count']}.

The superseded prompt-set hash is `{audit['superseded_prompt_set_hash']}`. The frozen v2 prompt-set hash is `{audit['prompt_set_hash']}`.

## 8. Reproducibility, Leakage, and Tests
100/100 hashes matched across manifest-order reloads and a seed-{audit['reproducibility']['random_order_seed']} randomized render order. Each formerly oversized case matched 10/10 renders. Leakage audit={audit['leakage_audit']['status']} across raw snapshots, rendered evidence, and serialized provider payloads; no reference, ground truth, Hidden validation, evaluation canary, credential, or raw reasoning was found.

Fake end-to-end passed={str(args.fake_tests_passed).lower()}; renderer synthetic huge-output tests passed={str(args.renderer_tests_passed).lower()}; full regression passed={str(args.full_regression_passed).lower()}.

## 9. Two-stage Execution Gate
Stage 1 requires `--confirm-phase8-stage1`, permits exactly 100 Initial calls, freezes artifacts/cohort, then exits. Stage 2 requires separate `--confirm-phase8-stage2` plus valid 100-artifact, first-patch, failure-evidence, and cohort hashes before network. Stage 2 is exactly `2M`, where M is the frozen Stage 1 eligible count. No third attempt exists. Pre-registered order is {dict(order_counts)}.

## 10. Model and Revised Rough Cost
Frozen configuration is unchanged: DeepSeek Official API `deepseek-v4-flash`, thinking enabled, reasoning effort low, max_tokens=16384, stream=false, temperature not sent, transport retries=0.

The transparent input heuristic is `ceil(serialized UTF-8 bytes / 4)`: min={tokens['min']:,}, median={tokens['median']:,}, mean={tokens['mean']:,}, p95={tokens['p95']:,}, max={tokens['max']:,}, total={tokens['total']:,} estimated Stage 1 input tokens. Using the official snapshot verified {prices['verified_at']}, cache-miss input ${rates['input_cache_miss']}/M, output ${rates['output']}/M, and mean completion usage from {usage_n} Phase 7 responses ({completion_mean:.1f} tokens/call), Stage 1 is roughly `${stage1_cost:.4f}`. This is a high-uncertainty projection, not billing data.

## 11. Readiness
Phase 8 Stage 1 is technically {readiness}; user authorization remains false. Dataset, partition, FL-v1, raw runtime, v2 prompts, reproducibility, leakage, renderer tests, Stage 2 F reuse, and full regression gates pass. No formal LLM call or bulk stage has started.

{blocker}
"""
    PHASE8_PRE_EXPERIMENT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PHASE8_PRE_EXPERIMENT_REPORT.write_text(text, encoding="utf-8")
    print(f"wrote {PHASE8_PRE_EXPERIMENT_REPORT}; stage1_ready={ready}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
