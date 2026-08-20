# Phase 8 Stage 1 Formal Experiment

## Scope

Stage 1 executed one frozen Initial repair attempt for each of 100 cases. It did not execute Retry Control or Execution Feedback calls and does not answer the paired R/F research question.

## Results

| Metric | Result |
| --- | ---: |
| Attempted / received / provider failure | 100 / 100 / 0 |
| Valid model outputs | 91 |
| Compile success | 91 |
| Repair-time success | 85 |
| Validated patches | 85 |
| Repair-time success but Hidden failure | 0 |
| Invalid model output / length truncation | 9 / 9 |
| Second-round eligible M | 6 |

Eligible failure distribution: `{"base_and_feedback_test_failure": 2, "base_repair_test_failure": 2, "feedback_test_failure": 2}`.

## Usage And Cost

- Prompt/cache-hit/cache-miss tokens: 777055 / 0 / 777055.
- Reasoning/final-answer/completion/total tokens: 595938 / 24729 / 620667 / 1397722.
- Finish reasons: `{"length": 9, "stop": 91}`.
- Response models: `{"deepseek-v4-flash": 100}`.
- System fingerprints: `{"a26a7955944dc5c60445bff77fac9c8e": 100}`.
- Stage 1 estimated cost from provider-reported usage: `$0.28257446`.
- Pricing snapshot: `2026-08-19T16:37:39Z`, cache hit `$0.0028`/M, cache miss `$0.14`/M, output `$0.28`/M.

## Frozen Artifacts

- Stage 1 artifact-set hash: `7336d3312e737ea39bab8144e88e82b45f0eff056ddee5ef363aa36289f4070b`.
- Eligible cohort manifest hash: `e1ec70b962cda0754c336896cd0975d2ef9794d410146c34223d50792797c9c5`.
- Stage 2 prompt audit hash: `a0254c9e1f73e16d67049da3c62052eec7032322407199945a99d9bbb381c39c`.
- R/F prompt candidates generated: 12 (6 paired cases).
- R bytes min/median/p95/max: 8867 / 15371.0 / 112631 / 112631.
- F bytes min/median/p95/max: 11618 / 16448.0 / 136634 / 136634.
- Reproducibility: `passed`.
- Leakage audit: `passed`.
- Payload hard gate: `passed`.
- R/F order balance: `{"feedback->retry_control": 4, "retry_control->feedback": 2}`.

## Stage 2 Projection

Expected real calls are `2M = 12`. Estimated cost is `$0.03607045`, using Stage 2 serialized-byte input estimates, cache-miss pricing, and the observed Stage 1 mean completion tokens. This is not a billing export.

Stage 2 technical readiness is evaluated separately. Stage 2 user authorization remains false, and no Stage 2 real LLM call has been made.
