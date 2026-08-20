# Phase 8 Controlled Execution Feedback Formal Experiment

## Research Question

For the same failed Stage 1 patch, does one retry with bounded execution feedback validate more often than the same retry opportunity without feedback?

## Frozen Cohort And Stage 1 Baseline

Stage 1 validated 85/100 patches. The frozen eligible cohort contains `M=6` repair-time failures. Each case used the same frozen first patch in R and F. R contains no first-patch execution feedback; F adds only Runtime Evidence Renderer v2 bounded repair-time failure evidence.

Stage 2 attempted/received/provider-failed calls: `12 / 12 / 0`. Each arm made one request with zero transport retries; the artifact field `repair_round=2` denotes the second repair round, while `arm_attempt=1` denotes one request per arm.

## Paired Results

| Outcome | Cases |
| --- | ---: |
| Both validated | 3 |
| R failed, F validated | 1 |
| R validated, F failed | 1 |
| Both failed | 1 |

- R validated: `4/6`.
- F validated: `4/6`.
- F-R validated difference: `0.000000` (0.0 percentage points).
- Gross F rescue among R failures: `0.500000`.
- Paired bootstrap 95% CI for F-R: `[-0.500000, 0.500000]`, using exact enumeration of empirical paired bootstrap resamples (46656 resamples).
- Exact two-sided McNemar: `p=1.000000` with 2 discordant pairs.

These are paired case-level observations. With `M=6`, the interval is wide and the study has little power for statistical generalization.

## Case Outcomes

| Case | R classification | F classification | R validated | F validated |
| --- | --- | --- | ---: | ---: |
| 315-A-bug-8649287-8687189 | repair_test_failed | validated_patch | false | true |
| 75-A-bug-15928172-15928345 | validated_patch | validated_patch | true | true |
| 365-A-bug-17262691-17262721 | validated_patch | validated_patch | true | true |
| 404-B-bug-14578678-14578704 | validated_patch | validated_patch | true | true |
| 366-B-bug-5240575-5240582 | validated_patch | invalid_model_output | true | false |
| 305-A-bug-13310851-13310872 | plausible_patch | plausible_patch | false | false |

## End-To-End Validated Rates

- S0, Initial only: `85/100 = 85.0%`.
- SR, Initial + retry without feedback: `89/100 = 89.0%`.
- SF, Initial + feedback retry: `89/100 = 89.0%`.

## Failure Analysis

- R classifications: `{"plausible_patch": 1, "repair_test_failed": 1, "validated_patch": 4}`.
- F classifications: `{"invalid_model_output": 1, "plausible_patch": 1, "validated_patch": 4}`.
- One R repair-time failure was rescued by F. One R validated patch became a length-truncated invalid F output. One case in each arm passed repair-time tests but failed Hidden Validation.

## Token Usage And Cost

- Total prompt/cache-hit/cache-miss tokens: `186245 / 168192 / 18053`.
- Total reasoning/final-answer/completion/total tokens: `115550 / 3010 / 118560 / 304805`.
- Usage-based Stage 2 cost estimate: `$0.03619516`.
- R tokens/cost: `{"cost_usd": 0.01687501, "tokens": {"completion_tokens": 58298, "final_answer_tokens": 1629, "prompt_cache_hit_tokens": 83840, "prompt_cache_miss_tokens": 2263, "prompt_tokens": 86103, "reasoning_tokens": 56669, "total_tokens": 144401}}`.
- F tokens/cost: `{"cost_usd": 0.01932015, "tokens": {"completion_tokens": 60262, "final_answer_tokens": 1381, "prompt_cache_hit_tokens": 84352, "prompt_cache_miss_tokens": 15790, "prompt_tokens": 100142, "reasoning_tokens": 58881, "total_tokens": 160404}}`.
- R/F details and provider metadata are retained in the hashed result manifest. Raw Stage 2 artifacts remain local and are excluded from Git because they are large reproducible records.

## Integrity And Limitations

- Stage 2 artifact-set hash: `cf4f44f802913085ce70d7da344a3952c014295f712954b0de93d58ab2c96a04`.
- Stage 2 result manifest hash: `bdc07d0be135edfc51e9c16c48c6163cead0cee6762654a30e0b76a483e4f95e`.
- Leakage audit: `passed`.
- `Validated Patch != Formally Correct Patch`: validation is limited to the registered Base, Feedback, and Hidden tests.
- `M=6` limits statistical generalization. Neither a large percentage nor a p-value would justify population-level claims here.

## Conclusion

In this frozen six-case cohort, execution feedback did not improve the aggregate validated count over retry alone: both validated 4/6, with one F rescue and one opposite-direction loss. The result is paired case-level evidence of heterogeneous effects, not evidence of a general advantage or disadvantage.
