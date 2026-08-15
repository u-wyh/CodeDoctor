# LLM Repair Evidence Ablation

## 1. Research Question

**Does fault-localization and execution evidence improve single-attempt LLM program repair?**

This report preregisters and implements the experiment, but the current environment had no API credential, base URL, or online model configured. Therefore no online A/B/C effectiveness result is claimed. Fake-provider smoke artifacts are explicitly excluded from all experimental metrics.

## 2. Dataset

- Selection seed: `20260817`.
- Static candidate count after excluding the prior sets: 3534; dynamically tested: 61.
- Final Repair Pilot: 50 cases; dynamic exclusions: 11 (reference_failed_repair_tests=5, reference_failed_validation_tests=6); static exclusions: 20.
- Overlap with the 50-case FL Pilot: 0; overlap with the 300-case independent FL Evaluation: 0.

## 3. Experimental Setup

- Protocol: `repair-v2`; prompt: `repair-evidence-v2`; one attempt per case/group.
- Group A: complete buggy source plus the common repair-time input/expected-output oracle.
- Group B: Group A plus frozen CodeDoctor FL-v1 Top-10 locations, or the uniform no-reliable-location message when FL-v1 itself produces no positive-score location.
- Group C: Group B plus runtime-only repair-test verdict, actual stdout/stderr, exit code, and timeout state. Input and expected output remain exclusively in the shared base context.
- Registered defaults: temperature 0.0, maximum output tokens 4096, request timeout 120 seconds. A seed is sent only when explicitly configured and supported; determinism is not assumed.
- Model/version: not configured; online calls: 0.
- Patch protocol: complete source extraction, Docker compilation, repair tests, then hidden validation for plausible patches. A validated patch means that all available repair and hidden validation tests pass; it is not formal correctness.

## 4. Leakage Boundary

`RepairContext` can contain only case ID, language, buggy source, the common repair-time oracle, registered FL-v1 locations/status, and runtime execution evidence. Reference source, ground-truth diff/lines, and hidden validation tests are held in a separate evaluation-only boundary and are not accepted by prompt rendering. The Codeflaws distribution has no per-case problem statements, so existing repair-test input/expected-output pairs serve as a versioned common oracle and are identical in A/B/C. Prompt canary tests and artifact scans cover `REFERENCE_SECRET_TOKEN` and `VALIDATION_SECRET_TOKEN`. API keys are neither serialized nor cached. Artifact boundary scan: `passed` over 9 artifacts.

## 5. Results

| Group | Cases | Valid output | Compile success | Plausible | Validated |
|---|---:|---:|---:|---:|---:|
| A | 0 | N/A | N/A | N/A | N/A |
| B | 0 | N/A | N/A | N/A | N/A |
| C | 0 | N/A | N/A | N/A | N/A |

| Comparison | Paired cases | Validated-rate difference | Bootstrap 95% CI | After-only/Before-only | Exact McNemar p |
|---|---:|---:|---:|---:|---:|
| B-A | 0 | N/A | N/A | N/A | N/A |
| C-B | 0 | N/A | N/A | N/A | N/A |
| C-A | 0 | N/A | N/A | N/A | N/A |

Online experiment status: `not_run_no_credentials`. These N/A cells are intentional and must not be replaced with fake-provider outcomes.

## 6. Failure Analysis

No online model failures are available for scientific analysis. The local fake-provider smoke ran 9 artifacts over 3 cases across A/B/C; classifications were {'repair_test_failed': 9}. The fake returned the buggy source unchanged, so this confirms context, extraction, Docker compilation, repair-test classification, artifact writing, and resume boundaries without estimating repair ability. A separate non-artifact evaluator check ran one reference source through repair plus hidden validation and reached `validated_patch`.

FL-v1 produced no reliable positive-score suspicious location for 1 of 50 Repair Pilot cases: ['103-A-bug-18288288-18288294']. These cases remain in A/B/C and receive the uniform no-reliable-location message in B/C.

The implemented online analysis distinguishes invalid output, compile error, still failing original failing tests, regression on previously passing repair tests, and validation overfitting. It also records line-diff size, whether an FL Top-10 line was modified, FL Top-1/5/10 hit strata, 0-PASS, non-executable fault, equivalence-class size, and coverage diversity.

## 7. Threats to Validity

- The 50-case Repair Pilot is small; paired confidence intervals may be wide.
- Results will depend on one selected LLM/model version and its stochastic behavior.
- Temperature zero and an optional seed do not guarantee provider determinism.
- Codeflaws programs and tests may not represent larger real-world C/C++ systems.
- Repair and hidden validation suites are incomplete; validated is not formally correct.
- Findings may be prompt-sensitive even though the A/B/C base instruction is fixed.
- No online credential was available in this run, so the core causal comparison remains unmeasured.

## 8. Conclusion

Phase 7 establishes a disjoint Repair Pilot, a frozen single-attempt protocol, auditable A/B/C prompts with identical task semantics, strict leakage boundaries, content-addressed resume, Docker patch validation, paired statistics, and reporting. It does **not** yet answer whether FL or execution evidence improves LLM repair because no genuine online model call was possible. Bulk online execution is guarded and requires explicit approval. The next valid operation is to configure one fixed OpenAI-compatible model, verify pricing, and run a small genuine smoke before pausing again for approval of the full 50-case A/B/C experiment.
