# CodeDoctor Phase 8 Pre-experiment Report

## 1. Research Question and Control
When an extracted first patch fails observable repair-time execution, does one retry with failed execution feedback outperform an otherwise identical retry without feedback? R controls for a second-call benefit; Initial versus F alone would confound retry opportunity with execution feedback. The primary causal comparison remains paired R versus F.

## 2. Independent Evaluation Set
The seed-20260820 set contains 100 cases. Overlap is FL Pilot=0, Independent FL Evaluation=0, Phase 7 Repair Pilot=0.

Exclusions total 453: buggy_passed_all_tests=1, fl_pipeline_failed=1, historical_dataset_overlap=400, insufficient_validation_tests=20, reference_failed_repair_tests=9, reference_failed_validation_tests=2, static_validation_failed=20. No FL performance attribute was used for selection.

## 3. Frozen Test and Information Boundary
Protocol `phase8_test_partition_v1` uses SHA-256(seed + case id), with `feedback_count=min(max(1,floor(n/4)),n-1)`. Totals: Base=446, Feedback=1001, Hidden=3123. Manifest hash: `fb6239e5b37c81ba4464e00d5505bac9be9296e2fe6d1fc0a2e42573893fb9b7`.

Base and Feedback are the common repair-time oracle. Hidden tests remain evaluation-only and cannot enter Initial, R, F, execution feedback, or retry eligibility. Initial = common oracle + FL-v1 + frozen buggy runtime. R = Initial + the same first patch + uniform retry instruction. F = R + bounded failed execution observations only. Compile/Base/Feedback failure is eligible; provider failure, invalid output, repair-time success, and Hidden-only failure are not.

## 4. Raw Runtime Evidence
Frozen buggy runtime covers 100 cases and 1447 public tests; each was executed exactly once with zero transport retries. Raw runtime manifest hash remains `943959cb626bb3f190e4a63a45a53c11fbab63781e8297907971f0f0a206f0a0`. Full stdout/stderr/exit/timeout/verdict observations remain immutable and auditable; no snapshot was truncated, normalized, replaced, or recaptured.

## 5. Oversized Payload Attribution
The superseded v1 Initial prompt set had 4 requests above 400,000 bytes and a maximum of 30,774,820 bytes. Component attribution uses canonical UTF-8 bytes and sums exactly to each serialized provider request:

- `404-B-bug-14578678-14578704` total=30,774,820; source=529; Base oracle=5,075,563; Feedback oracle=9,589,378; FL=1,028; runtime stdout=14,818,134; runtime stderr=0; runtime metadata=2,248; instruction/template=593; serialization overhead=1,287,347; oracle_oversize=True.
- `626-A-bug-16228568-16228576` total=29,468,503; source=946; Base oracle=265; Feedback oracle=1,134; FL=857; runtime stdout=25,817,498; runtime stderr=0; runtime metadata=1,104; instruction/template=593; serialization overhead=3,646,106; oracle_oversize=False.
- `361-B-bug-5055774-5055807` total=3,435,093; source=570; Base oracle=204; Feedback oracle=1,772,815; FL=762; runtime stdout=1,657,989; runtime stderr=0; runtime metadata=1,597; instruction/template=593; serialization overhead=563; oracle_oversize=True.
- `285-A-bug-3882169-3882175` total=1,400,995; source=229; Base oracle=272; Feedback oracle=748,305; FL=609; runtime stdout=649,304; runtime stderr=0; runtime metadata=1,222; instruction/template=593; serialization overhead=461; oracle_oversize=True.

The maximum case, `404-B-bug-14578678-14578704`, was jointly dominated by 14,664,941 bytes of common oracle representation and 14,818,134 bytes of runtime stdout. Three of the four cases had oversized common oracle fields, so a runtime-only fix would not satisfy the unchanged hard gate. Cases were not deleted or replaced, and the gate was not raised.

## 6. Bounded Prompt-visible Rendering
`phase8-runtime-evidence-render-v2` applies uniformly to all 100 Initial prompts and future Stage 2 F feedback. Every execution test retains test id, verdict, exit/timeout status, stdout/stderr byte lengths, and SHA-256 identities.

- Exact PASS stdout is represented as matching the already-public expected output, without duplicating its body.
- Clean-exit mismatch records first differing byte, expected/actual length and hash, plus at most 1,024 bytes before and 3,072 bytes after the difference from actual stdout. It adds no expected window or new specification.
- Abnormal stdout is full through 4,096 bytes; otherwise first/last 2,048 bytes with exact omitted count.
- stderr is full through 8,192 bytes; otherwise first/last 4,096 bytes.
- compiler stderr is full through 16,384 bytes; otherwise first/last 8,192 bytes.
- Common Oracle v2 applies identically to Initial/R/F: each input/expected field is full through 4,096 bytes, otherwise first/last 2,048 bytes with total length and SHA-256.
- UTF-8 is canonical; excerpts crossing a multibyte boundary use deterministic `errors=replace` decoding.

Raw observations and prompt-visible representations are separately hashed in artifacts through raw observation/manifest hashes, render protocol version, and rendered evidence hash. F reuses this exact renderer; R contains no execution feedback.

## 7. Before and After
- `285-A-bug-3882169-3882175`: 1,400,995 -> 27,515 bytes (ratio=0.01963961; 10/10 stable).
- `361-B-bug-5055774-5055807`: 3,435,093 -> 45,971 bytes (ratio=0.01338275; 10/10 stable).
- `404-B-bug-14578678-14578704`: 30,774,820 -> 111,833 bytes (ratio=0.00363391; 10/10 stable).
- `626-A-bug-16228568-16228576`: 29,468,503 -> 30,404 bytes (ratio=0.00103175; 10/10 stable).

Across 100 v2 serialized requests: min=5,494, median=15,867.5, mean=19,566.89, p95=45,971, max=111,833, total=1,956,689 bytes. Warning count above 300,000=0; hard-gate failures above 400,000=0.

The superseded prompt-set hash is `dd4127d97c7a73b822330d0c1c6890873e3913170b48335c895cca59b1b49672`. The frozen v2 prompt-set hash is `c4087dee0353c12fdbe1310ed314272f7436f2fc22560c9917da4dfc75a3f491`.

## 8. Reproducibility, Leakage, and Tests
100/100 hashes matched across manifest-order reloads and a seed-20260820 randomized render order. Each formerly oversized case matched 10/10 renders. Leakage audit=passed across raw snapshots, rendered evidence, and serialized provider payloads; no reference, ground truth, Hidden validation, evaluation canary, credential, or raw reasoning was found.

Fake end-to-end passed=true; renderer synthetic huge-output tests passed=true; full regression passed=true.

## 9. Two-stage Execution Gate
Stage 1 requires `--confirm-phase8-stage1`, permits exactly 100 Initial calls, freezes artifacts/cohort, then exits. Stage 2 requires separate `--confirm-phase8-stage2` plus valid 100-artifact, first-patch, failure-evidence, and cohort hashes before network. Stage 2 is exactly `2M`, where M is the frozen Stage 1 eligible count. No third attempt exists. Pre-registered order is {'F-first': 59, 'R-first': 41}.

## 10. Model and Revised Rough Cost
Frozen configuration is unchanged: DeepSeek Official API `deepseek-v4-flash`, thinking enabled, reasoning effort low, max_tokens=16384, stream=false, temperature not sent, transport retries=0.

The transparent input heuristic is `ceil(serialized UTF-8 bytes / 4)`: min=1,374, median=3,967.0, mean=4,892.07, p95=11,493, max=27,959, total=489,207 estimated Stage 1 input tokens. Using the official snapshot verified 2026-08-19T16:37:39Z, cache-miss input $0.14/M, output $0.28/M, and mean completion usage from 148 Phase 7 responses (5265.7 tokens/call), Stage 1 is roughly `$0.2159`. This is a high-uncertainty projection, not billing data.

## 11. Readiness
Phase 8 Stage 1 is technically ready; user authorization remains false. Dataset, partition, FL-v1, raw runtime, v2 prompts, reproducibility, leakage, renderer tests, Stage 2 F reuse, and full regression gates pass. No formal LLM call or bulk stage has started.

No formal blocker remains.
