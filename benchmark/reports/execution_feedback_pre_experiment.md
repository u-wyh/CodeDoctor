# CodeDoctor Phase 8 Pre-experiment Report

## 1. Research Question
When an extracted first patch fails observable repair-time execution, does one retry with failed execution feedback outperform one otherwise identical retry without feedback?

## 2. Why Retry Control Is Required
R controls for the benefit of a second model call. Initial versus F confounds retry opportunity with execution feedback; the primary causal comparison is paired R versus F.

## 3. Independent Evaluation Set
The seed-20260820 set contains 100 cases. Overlap is FL Pilot=0, Independent FL Evaluation=0, Phase 7 Repair Pilot=0.

Exclusions total 453: buggy_passed_all_tests=1, fl_pipeline_failed=1, historical_dataset_overlap=400, insufficient_validation_tests=20, reference_failed_repair_tests=9, reference_failed_validation_tests=2, static_validation_failed=20. The 400 historical overlaps and static exclusions are recorded; only 100 selected cases enter Phase 8. No FL performance attribute was used for selection.

## 4. Frozen Test Partition
Protocol `phase8_test_partition_v1` uses SHA-256(seed + case id), with `feedback_count=min(max(1,floor(n/4)),n-1)`. Totals: Base=446, Feedback=1001, Hidden=3123. Manifest hash: `fb6239e5b37c81ba4464e00d5505bac9be9296e2fe6d1fc0a2e42573893fb9b7`. Feedback/Hidden identities are namespaced to avoid source-pool test-id collisions.

Base and Feedback input/expected output are public before Initial. Hidden tests remain evaluation-only and cannot enter prompts, feedback, or retry eligibility.

## 5. Initial, R, and F
Initial = Base+Feedback public oracle + FL-v1 + frozen buggy runtime. R = identical Initial context + the frozen first patch + uniform retry instruction, with no execution feedback. F = R plus only failed repair-time compiler/test observations. R and F share the exact first patch.

## 6. Eligibility and Evaluation
Second-round eligible means an extractable source with compile failure, Base failure, or Feedback failure. Provider failure and invalid model output are ineligible. Repair-time success forbids retry even when Hidden validation later fails. Plausible means all Base+Feedback pass; Validated additionally means all Hidden tests pass and does not mean formally correct.

## 7. Runtime and Artifacts
Frozen buggy runtime covers 100 cases and 1447 public tests; each was executed exactly once with zero transport retries. Runtime manifest hash: `943959cb626bb3f190e4a63a45a53c11fbab63781e8297907971f0f0a206f0a0`.

Artifacts are content-addressed under `initial/`, `retry_control/`, and `feedback/`; they bind protocol, partition, prompt, first patch, failure evidence, model metadata, repair-time results, hidden evaluation results, and timestamps. API keys, raw reasoning, reference source, and ground-truth diffs are excluded.

## 8. Reproducibility and Leakage
Initial prompt audit: 100/100, prompt-set hash `dd4127d97c7a73b822330d0c1c6890873e3913170b48335c895cca59b1b49672`, independent reload hashes identical=true, leakage=passed. Operational size gate=failed. Canary tests cover Initial/R/F boundaries. Fake end-to-end scenarios passed=true, including compile failure, test failure, repair-time success, Hidden-only failure, invalid output, and provider failure.

## 9. Two-stage Execution Gate
Stage 1 requires `--confirm-phase8-stage1`, permits exactly 100 Initial calls, freezes artifacts/cohort, then exits. Stage 2 requires separate `--confirm-phase8-stage2` plus valid 100-artifact, first-patch, failure-evidence, and cohort hashes before network. Stage 2 is exactly `2M`, where M is the frozen Stage 1 eligible count. No third attempt exists. Pre-registered order across all 100 cases is {'F-first': 59, 'R-first': 41}.

## 10. Model and Rough Cost
Frozen configuration: DeepSeek Official API `deepseek-v4-flash`, thinking enabled, reasoning effort low, max_tokens=16384, stream=false, temperature not sent, transport retries=0.

Rough estimate uses mean observed Phase 7 formal usage (148 responses): 776.8 input and 5265.7 completion tokens per call, and the official pricing snapshot verified 2026-08-19T16:37:39Z (cache-miss input $0.14/M, output $0.28/M). Stage 1 is roughly $0.1583. Stage 2 is roughly `$0.001583 * 2M`; actual Phase 8 prompts, cache behavior, output length, and M are unknown, so uncertainty is high.

## 11. Readiness
Dataset, partition, FL-v1, runtime, Initial prompt reproducibility, leakage checks, fake tests, and fail-closed gates are prepared. Phase 8 Stage 1 is technically not ready; no formal LLM call or bulk stage has started.

Formal blocker: 4 Initial requests exceed the frozen 400000-byte operational gate; the largest is 30774820 bytes. The complete public oracle and frozen observations were not truncated or replaced.
