# LLM Repair Pre-Experiment Report

## Model And Provider

- Provider: **DeepSeek Official API**.
- API: OpenAI-compatible Chat Completions; base URL `https://api.deepseek.com`.
- Requested model ID: `deepseek-v4-pro`.
- Official documented model version: `DeepSeek-V4-Pro-0813`.
- Response model/version observed at experiment time: `not observed; no real response`.
- Thinking: `enabled`; reasoning effort: `high`; stream: `false`.
- Temperature: not sent and not an effective sampling control in thinking mode. Temperature-based determinism is not claimed.
- Maximum output tokens: 8192; maximum repair attempts: 1.
- `deepseek-v4-pro` is an API alias and may resolve differently over time; the response model and system fingerprint are recorded when available.

## Credential And Billing

- Independent API key required: yes; priority is `DEEPSEEK_API_KEY`, then `CODEDOCTOR_API_KEY`.
- `OPENAI_API_KEY` is not used as a DeepSeek fallback.
- Credential readiness: `False`; environment used: `none`. No secret value is stored or printed.
- Billing path: DeepSeek Official API balance.
- ChatGPT Plus/Codex subscription is separate from DeepSeek API billing.

## Calls And Smoke

- Repair Pilot: 50 frozen cases; groups: 3; attempts: 1.
- Formal bulk size: 150 primary calls. This bulk has not been started.
- Authorized smoke maximum: 3 calls; actual real smoke calls: 0.
- Smoke selection: `259-B-bug-13083263-13083279`, selected by `first case in the frozen Repair Pilot manifest`.
- Automatic transport retries: 0.

| Group | Real calls | Prompt tokens | Completion tokens | Reasoning tokens | Total tokens |
|---|---:|---:|---:|---:|---:|
| A | 0 | N/A | N/A | N/A | N/A |
| B | 0 | N/A | N/A | N/A | N/A |
| C | 0 | N/A | N/A | N/A | N/A |

- Smoke classifications: `N/A`.
- Finish reasons: `N/A`. A `length` finish reason or incomplete source requires a stop, not a parameter change.

## Token Projection

| Group | Calls | Approx. average input tokens | Approx. total input tokens |
|---|---:|---:|---:|
| A | 50 | ~380 | ~18800 |
| B | 50 | ~590 | ~29700 |
| C | 50 | ~690 | ~34400 |

- Previous output proxy for 150 calls: ~24600 tokens.
- Bulk projection basis: provider-independent character estimate; no real DeepSeek smoke usage.
- Projected A/B/C input tokens: `{'A': 18800, 'B': 29700, 'C': 34400}`.
- Projected output including provider-reported reasoning when real usage exists: `24600` tokens.
- Separately reported reasoning tokens: `N/A`.
- Estimation method: ceil(UTF-8-decoded character count / 4) per prompt/source; averages rounded to 10 tokens and totals to 100 tokens; buggy-source length is the complete-source output proxy until real usage exists.

## Official Pricing Verification

- Official source: https://api-docs.deepseek.com/quick_start/pricing/
- Verification time: `2026-08-16T02:49:39Z`; currency: USD; unit: 1M tokens.
- Price active at verification: cache hit `$0.003625`, cache miss `$0.435`, output `$0.87`.
- Scheduled peak/off-peak change effective `2026-08-16T16:00:00Z`.
- Off-peak: cache hit `$0.022`, cache miss `$0.66`, output `$1.98`.
- Peak: cache hit `$0.044`, cache miss `$1.32`, output `$3.96`.
- Peak windows: 01:00-04:00 UTC, 06:00-10:00 UTC; all other UTC hours are off-peak.
- Conservative all-cache-miss bulk cost at verification prices: **$0.057464**.
- Conservative all-cache-miss scheduled off-peak cost: **$0.103422**.
- Conservative all-cache-miss scheduled peak cost: **$0.206844**.
- Context cache is best-effort, so cache-hit pricing is not assumed.

## Information Boundary

| Information | A | B | C |
|---|---:|---:|---:|
| Buggy source | Yes | Yes | Yes |
| Common repair-time input/expected-output oracle | Same | Same | Same |
| FL-v1 evidence | No | Yes | Yes |
| Runtime verdict/actual output/exit status | No | No | Yes |
| Reference source | No | No | No |
| Ground-truth diff | No | No | No |
| Hidden validation | No | No | No |

- Reference leakage regression: `passed`.
- Validation leakage regression: `passed`.
- Manual prompt inspection: `passed`.
- Prompt boundary audit: `passed` over 150 prompts.
- Artifact boundary audit: `passed` over 9 artifacts.
- Reference source, ground-truth diff, hidden validation, and evaluation-only metadata absent: `passed` / `passed` / `passed` / `passed`.

## Mandatory Stop

- `bulk_online_ready = false`.
- `bulk_user_authorized = false`.

Blocking reasons:

- DeepSeek API credential unavailable
- three-call genuine DeepSeek smoke with usage and final content not complete

DeepSeek Phase 7 bulk experiment is technically not ready.

No 150-call bulk experiment has been started.

Awaiting explicit approval before using `--confirm-bulk`.
