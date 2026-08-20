# Final Engineering Cleanup and Fresh Clone Reproduction Audit

Date: 2026-08-20
Frozen source commit: `a5a028b1feabf5ae950eabbfdf77d5604d56c9ac`
Real LLM calls: `0`

## Scope

This is a maintenance audit of the frozen Phase 4-9 repository. It does not change fault localization, repair prompts or protocols, dataset partitions, validation rules, metadata, frozen artifacts, hashes, or final tables.

## Repository Structure

- `benchmark/` owns Codeflaws models, dataset manifests, formal metadata, reports, results, and phase-specific command-line scripts.
- `fault_localization/`, `repair/`, `repair_phase8/`, and `validation_phase9/` preserve the four frozen research parts.
- `sandbox/` owns local/Docker execution and sanitizer integration.
- `analysis/` contains structured sanitizer evidence models and parsing.
- `final_consolidation/` verifies frozen metrics and final registries.
- `docs/` contains the development and research documentation. Scripts and reports intentionally live under `benchmark/scripts/` and `benchmark/reports/`; there are no separate top-level `scripts/` or `reports/` directories.

No definite obsolete module, debug file, exact duplicate script, or unused module was found. Phase-specific build/run/report scripts have similar names but preserve distinct frozen protocols and are not interchangeable. Two `.orig`/`.backup` filenames occur only inside the ignored upstream raw Codeflaws dataset and are not tracked project debug files.

Candidate cleanup only: a conservative AST scan reported apparently unused imports in `benchmark/codeflaws.py`, `benchmark/reporting.py`, two benchmark scripts, three fault-localization modules, `repair/pre_experiment.py`, `repair_phase8/context.py`, `repair_phase8/reporting.py`, `validation_phase9/pipeline.py`, and `validation_phase9/reporting.py`. They were not edited because these modules belong to the frozen experimental implementation and the repository does not currently pin a linter that can confirm all typing/runtime cases.

## Files Larger Than 10 MB

| Bytes | Path | Class |
| ---: | --- | --- |
| 265,695,532 | `benchmark/datasets/codeflaws/downloads/codeflaws.tar.gz` | B - downloadable/re-extractable dataset archive |
| 150,111,683 | `benchmark/artifacts/repair_phase8/feedback/404-B-bug-14578678-14578704/086310553e926cb830342415e137872812097b4ef087fefea2da34e9c1189ff9.json` | A - local frozen formal raw artifact; summary/hash is tracked |
| 150,087,391 | `benchmark/artifacts/repair_phase8/retry_control/404-B-bug-14578678-14578704/ec162ced57c75e09394bb5629ac978ccc250a84c1263a303868a152adb78cb0e.json` | A - local frozen formal raw artifact; summary/hash is tracked |
| 54,430,433 | `benchmark/artifacts/repair_phase8/initial/404-B-bug-14578678-14578704/71988fd787a0732d704b8cff22e612141b43ff06eb71e1defa7aa7981ea8ce5f.json` | A - tracked frozen Phase 8 artifact |
| 41,241,634 | `benchmark/datasets/codeflaws/metadata/manifest.jsonl` | A - tracked dataset identity/metadata |
| 37,463,340 | `benchmark/datasets/codeflaws/raw/codeflaws/674-E-bug-17842470-17842486.tar.gz` | B - ignored upstream case archive |
| 29,467,463 | `benchmark/metadata/repair_phase8/runtime_evidence_v1/626-A-bug-16228568-16228576.json` | A - tracked frozen runtime evidence |
| 15,469,836 | `benchmark/metadata/repair_phase8/runtime_evidence_v1/404-B-bug-14578678-14578704.json` | A - tracked frozen runtime evidence |
| 13,308,613 | `benchmark/artifacts/repair_phase8/initial/361-B-bug-5055774-5055807/f03de0dd7f1a7ae1d63be7b33ca2cffda40d6a23c528078430108ff190fe6797.json` | A - tracked frozen Phase 8 artifact |

Five tracked files exceed 10,000,000 bytes. No class C temporary file larger than 10 MB was found. Git history was not rewritten.

## Ignore and Secret Audit

Raw/processed/downloaded Codeflaws data, Phase 6 intermediates, Phase 7 raw artifacts, Phase 8 Initial/R/F raw artifacts, Phase 9 generated inputs/evidence, build outputs, caches, logs, local environment files, keys, and common compiled binaries are ignored. This maintenance change adds explicit coverage for credential JSON names, log directories, and common object/library/executable outputs.

Tracked-file static secret scan result: `PASS`. No credential value, private key, non-example `.env`, or raw reasoning content was reported. The scan printed no matched content.

## README and Fresh Clone

The README now identifies CodeDoctor as an LLM-based automated program repair framework, lists the four core research modules, states environment requirements, links final results, and provides zero-API lightweight reproduction commands. It explicitly separates historical formal experiment runners from fresh-clone checks.

A candidate commit was exposed through a temporary Git ref and cloned inside the dedicated LXD Docker host. The clone was clean and contained all five final metadata files, 34 benchmark Python scripts, 19 final-table/plot files, the README, final report, and required smoke fixtures. Ignored raw Codeflaws data was correctly absent.

Fresh-clone smoke results:

- Final metadata/consolidation integrity: `7/7 PASS`.
- Docker sandbox sum example: `success`, stdout `3\n`.
- Benchmark model smoke: `3/3 PASS`.
- Fake-provider repair pipeline smoke: `1/1 PASS`; real provider calls `0`.
- Validation pipeline smoke: `5/5 PASS`.

## Regression and Reproduction Blockers

The complete current working copy, which retains ignored local raw data/artifacts, passed `177/177` tests with `0 FAIL` and `0 SKIP` in the LXD Docker host.

The fresh clone did not pass every full-suite test:

- `sandbox`: `29/29 PASS`.
- `benchmark`: `12/12 PASS`.
- `fault_localization`: `36/36 PASS`.
- `repair`: 47 run, 1 error because a production runtime-evidence test reads an ignored raw Codeflaws input file.
- `repair_phase8`: `28/28 PASS`.
- `validation_phase9`: 14 run with 2 errors; corpus/reporting tests require ignored Phase 7/9 raw artifacts.
- `final_consolidation`: setup error after the Phase 9 corpus path rewrote tracked `benchmark/results/repair/evidence_ablation.json` from an empty fresh-clone artifact store. The same final tests passed `7/7` before this preceding-suite pollution.

These are test-isolation and external-artifact dependency defects, not metric discrepancies. Fixing them safely requires changes in repair/validation test or reporting behavior, which is outside the user-authorized maintenance file set and touches frozen experimental code paths. No automatic fix was made. The temporary clone/ref was deleted and the LXD host was stopped.

## Code Quality

- Python syntax/bytecode compilation: `PASS`.
- Obvious debug breakpoint/TODO file audit: no actionable debug file found; command-line progress/output `print` calls are intentional.
- Exact duplicate benchmark script hash audit: none.
- C++17 `-Wall -Wextra -pedantic` smoke for `hello_world` and `sum`: `PASS`, no warnings; sum output was `7`.
- No whole-project formatting or frozen logic change was performed.

## Judgment

The tracked final metadata, reports, tables, isolated smoke path, and current artifact-complete checkout are reproducible. However, a raw-data-free fresh clone cannot run the complete existing regression cleanly and one Phase 9 test path can dirty a frozen tracked result when artifacts are absent. Therefore the repository is **not yet fully ready for thesis submission as a self-contained engineering artifact**. Resolving this requires explicit authorization for a narrowly scoped test-isolation/fail-closed maintenance change in frozen-adjacent repair/validation code.
