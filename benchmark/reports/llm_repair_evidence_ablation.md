# LLM Repair Evidence Ablation

## 1. Research Questions

**Does fault-localization and execution evidence improve single-attempt LLM program repair?**

RQ1 compares Group B with A to estimate the association of frozen FL-v1 evidence with validated repair. RQ2 compares Group C with B to estimate the incremental association of frozen runtime evidence. C versus A reports their combined difference. All results are paired at case level; descriptive subgroup results are not filtering rules or new experiments.

## 2. Frozen Experimental Protocol

- Protocol `repair-v2`, prompt `repair-evidence-v2`, one attempt per case/group, transport retries 0.
- Formal artifacts were completed from 2026-08-19T14:15:41.301492+00:00 to 2026-08-19T16:35:12.180421+00:00; requests attempted 150, responses received 148, resume used `false`.
- Runtime Evidence manifest hash: `96aa507caf2332d0f44b4f2fd3d0aaf68d1168e93856d046d57495b12a52ea3c`.
- Frozen formal prompt-set hash: `9a65e8fcf2eea3d3da8a64bbfac4d32736e9090da7917da4ea6270d7cb9eaea0`; artifact prompt hashes match: `true`.
- Formal artifact set hash: `067710f9f3b71855cc4bf1db3dd0614cef89c1d4cec7e4f6e83c0372b7607f17`; unique cache keys 150/150; attempt-one-only `true`; formal-role-only `true`.
- The 6 DeepSeek engineering smoke artifacts and 9 fake-provider artifacts are excluded from formal effectiveness metrics.

## 3. Dataset / Repair Pilot

- Selection seed: `20260817`.
- Static candidate count after excluding the prior sets: 3534; dynamically tested: 61.
- Final Repair Pilot: 50 cases; dynamic exclusions: 11 (reference_failed_repair_tests=5, reference_failed_validation_tests=6); static exclusions: 20.
- Overlap with the 50-case FL Pilot: 0; overlap with the 300-case independent FL Evaluation: 0.

## 4. Model and Provider

- Provider: DeepSeek Official API; model `deepseek-v4-flash`; observed response model `deepseek-v4-flash` and system fingerprint recorded per response.
- Thinking enabled, reasoning effort low, max tokens 16384, stream false, temperature and seed not sent, request timeout 120 seconds.
- Received 148 responses; the two absent responses are retained as infrastructure/API failures and were not retried.

## 5. A/B/C Definitions

- Group A: complete buggy source plus the common repair-time input/expected-output oracle.
- Group B: Group A plus frozen CodeDoctor FL-v1 Top-10 locations, or the uniform no-reliable-location message when FL-v1 itself produces no positive-score location.
- Group C: Group B plus runtime-only repair-test verdict, actual stdout/stderr, exit code, and timeout state. Input and expected output remain exclusively in the shared base context.
- Patch protocol: complete-source extraction, Docker compilation, repair tests, then hidden validation for plausible patches.

## 6. Leakage Boundary

`RepairContext` can contain only case ID, language, buggy source, the common repair-time oracle, registered FL-v1 locations/status, and runtime execution evidence. Reference source, ground-truth diff/lines, and hidden validation tests are held in a separate evaluation-only boundary and are not accepted by prompt rendering. The Codeflaws distribution has no per-case problem statements, so existing repair-test input/expected-output pairs serve as a versioned common oracle and are identical in A/B/C. Prompt canary tests and artifact scans cover `REFERENCE_SECRET_TOKEN` and `VALIDATION_SECRET_TOKEN`. API keys are neither serialized nor cached. Artifact boundary scan: `passed` over 165 artifacts.

## 7. Main Results

| Group | Cases | Valid output | Compile success | Plausible | Validated patch |
|---|---:|---:|---:|---:|---:|
| A | 50 | 46 (92.00%) | 46 (92.00%) | 43 (86.00%) | 40 (80.00%) |
| B | 50 | 47 (94.00%) | 47 (94.00%) | 42 (84.00%) | 39 (78.00%) |
| C | 50 | 50 (100.00%) | 50 (100.00%) | 49 (98.00%) | 46 (92.00%) |

Validated Patch means all available repair and hidden validation tests passed. **Validated Patch is not Formally Correct Patch.**

## 8. Paired Comparison

| Comparison | Paired cases | Before fail / after success | Before success / after fail | Validated-rate difference |
|---|---:|---:|---:|---:|
| B-A | 50 | 5 | 6 | -2.00% |
| C-B | 50 | 8 | 1 | +14.00% |
| C-A | 50 | 8 | 2 | +12.00% |

## 9. Paired Bootstrap 95% CI

| Comparison | Observed difference | 95% CI | Samples | Seed |
|---|---:|---:|---:|---:|
| B-A | -2.00% | [-14.00%, +12.00%] | 10000 | 20260817 |
| C-B | +14.00% | [+4.00%, +26.00%] | 10000 | 20260817 |
| C-A | +12.00% | [+0.00%, +24.00%] | 10000 | 20260817 |

The interval is a percentile paired bootstrap over 50 case-level validated/not-validated differences. It is descriptive uncertainty for this frozen Pilot and model run.

## 10. Exact McNemar Results

| Comparison | Before fail / after success | Before success / after fail | Discordant | Exact two-sided p |
|---|---:|---:|---:|---:|
| B-A | 5 | 6 | 11 | 1 |
| C-B | 8 | 1 | 9 | 0.0390625 |
| C-A | 8 | 2 | 10 | 0.109375 |

The p-values are exact, two-sided, and unadjusted for the three reported comparisons. No protocol or hypothesis was changed in response to them.

## 11. Failure Analysis

| Group | Model/API error | Invalid model output | Compile error | Repair-test failed | Plausible but validation failed | Validated patch |
|---|---:|---:|---:|---:|---:|---:|
| A | 1 | 3 | 0 | 3 | 3 | 40 |
| B | 1 | 2 | 0 | 5 | 3 | 39 |
| C | 0 | 0 | 0 | 1 | 3 | 46 |

The two model/API failures were one request timeout and one URL-open timeout for the same case in A/B; transport retry remained 0. Invalid outputs were length-truncated responses with no extractable final source. No failed, uncompilable, implausible, or overfitting patch was retried.

## 12. FL Quality vs Repair Outcome

| Descriptive subgroup | Cases | A validated | B validated | C validated |
|---|---:|---:|---:|---:|
| FL reliable | 49 | 81.63% | 79.59% | 91.84% |
| FL unreliable | 1 | 0.00% | 0.00% | 100.00% |
| FL Top-1 hit | 8 | 75.00% | 62.50% | 87.50% |
| FL Top-5 hit | 25 | 84.00% | 72.00% | 88.00% |
| FL Top-10 hit | 38 | 78.95% | 73.68% | 89.47% |
| FL Top-10 miss | 12 | 83.33% | 91.67% | 100.00% |
| 0-PASS | 13 | 76.92% | 69.23% | 100.00% |
| >=1 PASS | 37 | 81.08% | 81.08% | 89.19% |
| Non-executable fault | 4 | 100.00% | 100.00% | 100.00% |
| Executable fault | 46 | 78.26% | 76.09% | 91.30% |
| Fault equivalence singleton | 2 | 100.00% | 50.00% | 100.00% |
| Fault equivalence tied | 44 | 77.27% | 77.27% | 90.91% |
| Straight-line ambiguity | 36 | 77.78% | 77.78% | 91.67% |
| Coverage diversity lower half | 25 | 80.00% | 84.00% | 96.00% |
| Coverage diversity upper half | 25 | 80.00% | 72.00% | 88.00% |

FL-v1 had no reliable positive-score location for 1 case: ['103-A-bug-18288288-18288294']. Coverage diversity uses a post-hoc descriptive Pilot median split at 0.146429. These Top-k, 0-PASS, executable-fault, equivalence-class, ambiguity, and diversity summaries are exploratory and were not used to remove cases or rerun the model.

## 13. Token Usage / API Cost

| Group | Usage records/calls | Prompt | Cache hit | Cache miss | Reasoning | Final answer | Completion | Total | Estimated USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 49/50 | 23986 | 0 | 23986 | 282420 | 11876 | 294296 | 318282 | $0.085761 |
| B | 49/50 | 41883 | 20864 | 21019 | 254225 | 12445 | 266670 | 308553 | $0.077669 |
| C | 50/50 | 49101 | 39040 | 10061 | 205729 | 12632 | 218361 | 267462 | $0.062659 |

- Aggregate usage-bearing responses: 148/150; calls without usage: 2.
- Aggregate prompt/cache-hit/cache-miss tokens: 114970 / 59904 / 55066.
- Aggregate reasoning/final-answer/completion/total tokens: 742374 / 36953 / 779327 / 894297.
- Actual-usage cost estimate: `$0.226089` using the [DeepSeek Official API prices](https://api-docs.deepseek.com/quick_start/pricing/) verified at `2026-08-19T16:37:39Z`: cache hit `$0.0028`/M, cache miss `$0.14`/M, output `$0.28`/M. The two failed requests report no usage and therefore contribute no token-based cost estimate.

## 14. Threats to Validity

- The 50-case Repair Pilot is small; paired confidence intervals may be wide.
- Results depend on one selected mutable provider alias, one observed fingerprint, and stochastic model behavior.
- Codeflaws programs and tests may not represent larger real-world C/C++ systems.
- Repair and hidden validation suites are incomplete; validated is not formally correct.
- Findings may be prompt-sensitive even though the A/B/C base instruction is fixed.
- Two provider failures count as not validated; conclusions may differ under another independently preregistered run, but this run cannot be repaired post hoc.
- The three paired p-values are reported without multiplicity adjustment and should not be read as three independent confirmatory tests.
- Subgroup analyses are small, overlapping, and descriptive; they do not establish causal moderation.
- Token cost is computed from provider-reported usage and the official price snapshot, not an account billing export.

## 15. Conclusion

On this frozen 50-case run, Group B did not improve over A: 78% versus 80%, difference -2 percentage points, bootstrap 95% CI [-14, +12], exact McNemar p=1. Group C reached 92%, improving over B by 14 points with bootstrap 95% CI [+4, +26] and exact McNemar p=0.0390625; C exceeded A by 12 points, CI [0, +24], p=0.109375. Thus RQ1 provides no evidence that FL-v1 alone improved validated repair in this run, while RQ2 shows a positive paired association for adding frozen runtime evidence. The Pilot, incomplete test oracle, stochastic provider, multiple descriptive comparisons, and non-formal meaning of validation prevent broader correctness or causal claims.
