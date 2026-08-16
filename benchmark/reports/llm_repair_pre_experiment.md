# LLM Repair Pre-Experiment Report

## Candidate Selection Timeline

- Initial candidate: `deepseek-v4-pro`, thinking enabled, reasoning effort `high`, max tokens 8192.
- Pro smoke: 3/3 finish_reason=length with 8192 reasoning/completion tokens and empty final content.
- Decision: the Pro configuration was rejected before any formal bulk call and is marked `superseded pre-experiment smoke`; its 3 artifacts remain available only for engineering audit.
- Final candidate: `deepseek-v4-flash`, thinking enabled, reasoning effort `low`, max tokens 16384.
- Selection reason: pre-experiment output-budget compatibility failure, not post-hoc repair-result optimization.
- Decision timing: before the 150-call formal experiment; neither Pro nor Flash smoke contributes to future formal repair rates.

## Model And Provider

- Provider: **DeepSeek Official API**.
- API: OpenAI-compatible Chat Completions; base URL `https://api.deepseek.com`.
- Requested model ID: `deepseek-v4-flash`.
- Official documented model version: `DeepSeek-V4-Flash-0731`.
- Response model/version observed at experiment time: `deepseek-v4-flash`.
- Thinking: `enabled`; reasoning effort: `low`; stream: `false`.
- Temperature: not sent and not an effective sampling control in thinking mode. Temperature-based determinism is not claimed.
- Maximum output tokens: 16384; maximum repair attempts: 1.
- `deepseek-v4-flash` is an API alias and may resolve differently over time; the response model and system fingerprint are recorded when available.

## Credential And Billing

- Independent API key required: yes; priority is `DEEPSEEK_API_KEY`, then `CODEDOCTOR_API_KEY`.
- `OPENAI_API_KEY` is not used as a DeepSeek fallback.
- Credential readiness: `True`; environment used: `DEEPSEEK_API_KEY`. No secret value is stored or printed.
- Billing path: DeepSeek Official API balance.
- ChatGPT Plus/Codex subscription is separate from DeepSeek API billing.

## Calls And Smoke

- Repair Pilot: 50 frozen cases; groups: 3; attempts: 1.
- Formal bulk size: 150 primary calls. This bulk has not been started.
- Authorized smoke maximum: 3 calls; actual real smoke calls: 3.
- Superseded Pro engineering smoke calls retained but excluded: 3.
- Formal experiment calls: 0.
- Smoke selection: `259-B-bug-13083263-13083279`, selected by `first case in the frozen Repair Pilot manifest`.
- Automatic transport retries: 0.

| Group | Real calls | Prompt tokens | Completion tokens | Reasoning tokens | Final-answer tokens | Cache hit | Cache miss | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1 | 658 | 11154 | 10818 | 336 | 0 | 658 | 11812 |
| B | 1 | 1123 | 5285 | 4903 | 382 | 640 | 483 | 6408 |
| C | 1 | 1275 | 11005 | 10623 | 382 | 1024 | 251 | 12280 |

- Smoke classifications: `{'A': 'validated_patch', 'B': 'validated_patch', 'C': 'validated_patch'}`.
- Requested models: `{'A': 'deepseek-v4-flash', 'B': 'deepseek-v4-flash', 'C': 'deepseek-v4-flash'}`.
- Response models: `{'A': 'deepseek-v4-flash', 'B': 'deepseek-v4-flash', 'C': 'deepseek-v4-flash'}`.
- System fingerprints: `{'A': 'a26a7955944dc5c60445bff77fac9c8e', 'B': 'a26a7955944dc5c60445bff77fac9c8e', 'C': 'a26a7955944dc5c60445bff77fac9c8e'}`.
- Final content present: `{'A': True, 'B': True, 'C': True}`; extraction: `{'A': 'success', 'B': 'success', 'C': 'success'}`.
- Extracted source hashes: `{'A': '9dab2cd2619689fb3f7e4110cbd6774ea4aabe64cd7d730df72958d0b6f5a830', 'B': 'c870fc04751a285bfa802c8e638ef9397c3b0c1bad93afa6d2cf07302aafb846', 'C': '726f3c43448b6a7962545f9a108760135a68540cdf700ed45cff60e3f790f3dc'}`.
- Compile success: `{'A': True, 'B': True, 'C': True}`; plausible: `{'A': True, 'B': True, 'C': True}`; validated: `{'A': True, 'B': True, 'C': True}`.
- Finish reasons: `{'A': 'stop', 'B': 'stop', 'C': 'stop'}`. A `length` finish reason or incomplete source requires a stop, not a parameter change.
- Possible token truncation: `False`.

## Token Projection

| Group | Calls | Approx. average input tokens | Approx. total input tokens |
|---|---:|---:|---:|
| A | 50 | ~380 | ~18800 |
| B | 50 | ~590 | ~29700 |
| C | 50 | ~690 | ~34400 |

- Previous output proxy for 150 calls: ~24600 tokens.
- Bulk projection basis: full-Pilot character estimates calibrated by each smoke group's actual DeepSeek prompt-token ratio.
- Input calibration ratios A/B/C: `{'A': 1.629, 'B': 1.709, 'C': 1.698}`.
- Projected A/B/C input tokens: `{'A': 30600, 'B': 50800, 'C': 58400}`.
- Projected output including provider-reported reasoning when real usage exists: `1372200` tokens.
- Separately reported reasoning tokens: `1317200`.
- Output basis: one real completion per group multiplied by 50.
- Estimate uncertainty: high; one smoke case is not representative.
- Estimation method: ceil(UTF-8-decoded character count / 4) per prompt/source; averages rounded to 10 tokens and totals to 100 tokens; buggy-source length is the complete-source output proxy until real usage exists.

## Official Pricing Verification

- Official source: https://api-docs.deepseek.com/quick_start/pricing/
- Verification time: `2026-08-16T03:52:47Z`; currency: USD; unit: 1M tokens.
- Price active at verification: cache hit `$0.0028`, cache miss `$0.14`, output `$0.28`.
- Scheduled peak/off-peak change effective `2026-08-16T16:00:00Z`.
- Off-peak: cache hit `$0.007`, cache miss `$0.22`, output `$0.66`.
- Peak: cache hit `$0.014`, cache miss `$0.44`, output `$1.32`.
- Peak windows: 01:00-04:00 UTC, 06:00-10:00 UTC; all other UTC hours are off-peak.
- Conservative all-cache-miss bulk cost at verification prices: **$0.403788**.
- Conservative all-cache-miss scheduled off-peak cost: **$0.936408**.
- Conservative all-cache-miss scheduled peak cost: **$1.872816**.
- Context cache is best-effort, so cache-hit pricing is not assumed.
- Actual three-call smoke cost at verification prices: `$0.007884`.

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
- Artifact boundary audit: `passed` over 15 artifacts.
- Reference source, ground-truth diff, hidden validation, and evaluation-only metadata absent: `passed` / `passed` / `passed` / `passed`.

## Mandatory Stop

- `smoke_technical_ready = true`.
- `bulk_online_ready = false`.
- `bulk_user_authorized = false`.
- Remaining reproducibility blocker: `450-B-bug-15950152-15950193` is `unresolved`; Group C runtime actual output can change across baseline runs. The case remains in the Pilot.

Blocking reasons:

- 450-B runtime evidence reproducibility rule not frozen

DeepSeek Phase 7 bulk experiment is technically not ready.

No 150-call bulk experiment has been started.

Do not use `--confirm-bulk`.

Awaiting explicit approval before the Phase 7 bulk experiment.
