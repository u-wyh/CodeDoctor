# LLM Repair Pre-Experiment Report

## Model And Provider

- Model/version: `not selected`.
- Provider interface: OpenAI-compatible Chat Completions (actual service not selected).
- Base URL configured: False.
- Independent API key required: yes; read from `CODEDOCTOR_API_KEY`, falling back to `OPENAI_API_KEY`.

## Billing

- Billing path: not selected.
- Pricing: **not verified**; estimated API cost is intentionally unavailable.
- ChatGPT Plus/Codex subscription and API billing are separate; no shared quota is assumed.

## Expected Calls

- Repair Pilot: 50 cases; groups: 3; repair attempts: 1.
- Primary online calls: 150.
- Genuine smoke maximum before the bulk pause: 9 calls.
- Automatic transport retries: 0; a transport retry is not a second repair attempt.

## Token Estimate

| Group | Calls | Approx. average input tokens | Approx. total input tokens |
|---|---:|---:|---:|
| A | 50 | ~380 | ~18800 |
| B | 50 | ~590 | ~29700 |
| C | 50 | ~690 | ~34400 |

- Approximate expected output per call: ~160 tokens.
- Approximate total output for 150 calls: ~24600 tokens.
- Method: ceil(UTF-8-decoded character count / 4) per prompt/source; averages rounded to 10 tokens and totals to 100 tokens; buggy-source length is the expected complete-source output proxy.

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
- Reference source, ground-truth diff, hidden validation, and evaluation-only metadata absent: `passed` / `passed` / `passed` / `passed`.

## Mandatory Stop

Bulk online ready: `False`.

Blocking reasons:

- model/version not selected
- provider/base URL not selected
- independent API credential not configured
- genuine online smoke not run
- provider pricing not verified
- explicit user approval for bulk calls not granted

The CLI refuses more than nine online calls unless `--confirm-bulk` is supplied after explicit user approval. No bulk call is authorized by API-key availability, a successful smoke, or a ChatGPT/Codex subscription.
