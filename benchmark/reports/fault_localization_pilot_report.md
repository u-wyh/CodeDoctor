# Codeflaws Pilot Spectrum-Based Fault Localization Report

This report is generated from saved per-test gcov matrices, suspicious-line rankings, and evaluation-only diff ground truth. Validation tests and reference coverage are not used by localization.

## Experiment Population

| Metric | Actual result |
| --- | ---: |
| Pilot cases | 50 |
| Participating in SBFL | 50 |
| Not localizable | 0 |
| Cases with no passing repair test | 10 |
| Repair tests | 180 (92 PASS / 88 FAIL) |
| FAIL execution modes | 85 output mismatches with exit 0 / 3 nonzero exits / 0 timeouts |

All Pilot cases contain at least one failing repair test. Cases with no passing repair test remain mathematically localizable, but are marked because they provide no successful-execution contrast.

## Coverage Statistics

| Per-case measure | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: |
| PASS repair tests | 0 | 2.0 | 1.84 | 10 |
| FAIL repair tests | 1 | 1.0 | 1.76 | 4 |
| Executable source lines | 4 | 17.0 | 20.66 | 59 |

Each repair test starts from a clean `.gcno` workspace in a fresh constrained Docker container. Its `.gcda` and gcov JSON are therefore test-local. Coverage builds inject a small signal handler with GCC `-include`; for fatal signals it calls `__gcov_dump()` and re-raises the same signal, preserving the runtime verdict while retaining pre-crash coverage.

## Algorithm Results

| Algorithm | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| ochiai | 5/50 (10.00%) | 16/50 (32.00%) | 23/50 (46.00%) | 31/50 (62.00%) | 0.2601 |
| tarantula | 5/50 (10.00%) | 16/50 (32.00%) | 23/50 (46.00%) | 31/50 (62.00%) | 0.2595 |
| dstar2 | 5/50 (10.00%) | 16/50 (32.00%) | 23/50 (46.00%) | 31/50 (62.00%) | 0.2601 |

Ochiai, Tarantula, and DStar2 have different numeric scales, but this Pilot's coarse spectra often induce the same ordering buckets. DStar2's zero denominator with `ef > 0` is represented by the largest finite IEEE-754 value so JSON remains standards-compliant.

## Ties And Top-K

Rankings sort by suspiciousness descending and line number ascending. `rank` is this deterministic position; every item also records `tie_start_rank` and `tie_end_rank`.

| Algorithm | Cases with top-score tie | Cases with tied fault line |
| --- | ---: | ---: |
| ochiai | 48 | 47 |
| tarantula | 48 | 47 |
| dstar2 | 48 | 47 |

A fault line tied across a Top-K boundary may be counted differently under another deterministic tie-break. The reported metrics use line-number ordering for reproducibility; they are not tie-aware best-case scores.

## Typical Successes

### `133-A-bug-18286216-18286228`

- Repair tests: 2 PASS / 1 FAIL; executable lines: 11.
- Evaluation-only fault lines: [13].
- Buggy snippets: L13: string[i] == '9' || string[i] == '+') {.
- ochiai: first fault rank 1, score 0.707107, spectrum (1, 1, 0, 1), tie interval [1, 3].
- tarantula: first fault rank 1, score 0.666667, spectrum (1, 1, 0, 1), tie interval [1, 3].
- dstar2: first fault rank 1, score 1, spectrum (1, 1, 0, 1), tie interval [1, 3].
- Interpretation: failing-test coverage concentrates on the changed buggy-side line strongly enough to place it near the front, although its tie interval still shows how much ordering comes from the deterministic line-number rule.

### `370-A-bug-15330051-15330091`

- Repair tests: 2 PASS / 1 FAIL; executable lines: 35.
- Evaluation-only fault lines: [38].
- Buggy snippets: L38: if(abs(r1-r2)%2==0&&abs(c1-c2)%2==0).
- ochiai: first fault rank 1, score 1, spectrum (1, 0, 0, 2), tie interval [1, 6].
- tarantula: first fault rank 1, score 1, spectrum (1, 0, 0, 2), tie interval [1, 6].
- dstar2: first fault rank 1, score 1.79769e+308, spectrum (1, 0, 0, 2), tie interval [1, 6].
- Interpretation: failing-test coverage concentrates on the changed buggy-side line strongly enough to place it near the front, although its tie interval still shows how much ordering comes from the deterministic line-number rule.

## Typical Failures

### `471-A-bug-18116605-18116641`

- Repair tests: 3 PASS / 1 FAIL; executable lines: 15.
- Evaluation-only fault lines: [4, 20].
- Buggy snippets: L4: {; L20: {.
- ochiai: miss; fault line is not in the gcov executable-line ranking. Top line is L21 `a=0;` with (ef, ep, nf, np)=(1, 2, 0, 1).
- tarantula: miss; fault line is not in the gcov executable-line ranking. Top line is L21 `a=0;` with (ef, ep, nf, np)=(1, 2, 0, 1).
- dstar2: miss; fault line is not in the gcov executable-line ranking. Top line is L21 `a=0;` with (ef, ep, nf, np)=(1, 2, 0, 1).
- Interpretation: line-level gcov has no executable record for the diff ground truth, so no spectrum formula can rank that line. This is a representation mismatch, not an arithmetic failure.

### `66-A-bug-13987166-13987365`

- Repair tests: 2 PASS / 2 FAIL; executable lines: 13.
- Evaluation-only fault lines: [14].
- Buggy snippets: L14: 3,"bytes","127" ,.
- ochiai: miss; fault line is not in the gcov executable-line ranking. Top line is L30 `printf("%s",rango[i].tipo);` with (ef, ep, nf, np)=(2, 1, 0, 1).
- tarantula: miss; fault line is not in the gcov executable-line ranking. Top line is L30 `printf("%s",rango[i].tipo);` with (ef, ep, nf, np)=(2, 1, 0, 1).
- dstar2: miss; fault line is not in the gcov executable-line ranking. Top line is L30 `printf("%s",rango[i].tipo);` with (ef, ep, nf, np)=(2, 1, 0, 1).
- Interpretation: line-level gcov has no executable record for the diff ground truth, so no spectrum formula can rank that line. This is a representation mismatch, not an arithmetic failure.

## Comparison And Findings

- Coverage contrast is effective when the changed line is executable and is reached by failing tests more selectively than by passing tests.
- Correlated execution creates large tie groups. Formula changes cannot recover semantic distinctions absent from the spectrum.
- Ground-truth lines omitted from gcov executable records are guaranteed misses for statement-level SBFL and require a separately documented evaluation mapping if future work chooses to project them to executable neighbors.
- The 10 all-failing cases show why a failing test alone is insufficient for strong localization: Tarantula collapses covered failing lines to the same score when no passing execution exists.

## Scope And Limitations

The experiment covers 50 C defects under GCC/gcov 12.2.0. Ground truth comes from evaluation-only textual diff and is never passed to coverage, spectrum, formulas, or ranking. Results are sensitive to the Pilot tests, line-level gcov granularity, diff mapping, and deterministic handling of ties; they do not establish semantic causality.
