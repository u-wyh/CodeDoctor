# Independent Fault Localization Evaluation

Method `fl-v1` was frozen before selecting this independent set. Ground truth, reference source, validation tests, and buggy/reference diffs were used only after ranking. The artifact leakage scan passed for all 300 cases.

## Dataset

- Pilot: 50 cases; Evaluation: 300 cases; overlap: 0.
- Fixed seed: `20260816`; static exclusions: 20; dynamic exclusions: 22; recorded exclusions: 42.
- Dynamic exclusion reasons: buggy_passed_all_tests=4, reference_failed_repair_tests=14, reference_failed_validation_tests=4.
- Repair tests: 1194 total, 708 PASS and 486 FAIL.
- Defect classes (39): DCCA=8, DCCR=9, DMAA=8, DRAC=3, DRVA=9, DRWV=9, HBRN=9, HCOM=8, HDIM=5, HDMS=9, HEXP=8, HIMS=6, HOTH=9, OAAN=9, OAID=8, OAIS=7, OEDE=9, OFFN=6, OFPF=9, OFPO=9, OICD=5, OILN=8, OIRO=7, OITC=8, OLLN=8, OMOP=8, ORRN=8, SDFN=8, SDIB=6, SDIF=8, SDLA=8, SIIF=7, SIRT=7, SISA=8, SISF=7, SMOV=8, SMVB=8, SRIF=8, STYP=8.

## Baseline And FL-v1

| Method | Top-1 | Top-3 | Top-5 | Top-10 | MRR | Average-rank MRR | Pessimistic MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original Ochiai | 12.33% | 30.33% | 44.00% | 68.67% | 0.2773 | 0.2552 | 0.1880 |
| Branch-aware FL-v1 | 18.33% | 40.00% | 52.33% | 72.33% | 0.3475 | 0.3456 | 0.3004 |

## Improvement

| Metric | Original | Branch-aware | Absolute | Relative |
|---|---:|---:|---:|---:|
| Top-1 | 0.1233 | 0.1833 | +0.0600 | +48.65% |
| Top-3 | 0.3033 | 0.4000 | +0.0967 | +31.87% |
| Top-5 | 0.4400 | 0.5233 | +0.0833 | +18.94% |
| Top-10 | 0.6867 | 0.7233 | +0.0367 | +5.34% |
| MRR | 0.2773 | 0.3475 | +0.0702 | +25.32% |
| Average-rank MRR | 0.2552 | 0.3456 | +0.0904 | +35.41% |

On the primary tie-aware average-rank reciprocal outcome, 99 cases improved, 79 were unchanged, and 122 regressed. Deterministic reciprocal rank changed in 84/140/76 cases (improved/unchanged/regressed).

## Statistical Uncertainty

- Deterministic MRR difference: +0.0702; 95% paired bootstrap CI [+0.0432, +0.0986], 10000 samples, seed `20260816`.
- Average-rank MRR difference: +0.0904; 95% paired bootstrap CI [+0.0671, +0.1156], 10000 samples, seed `20260816`.

| Outcome | Original only | FL-v1 only | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|
| Top-1 | 3 | 21 | 24 | 0.000277162 |
| Top-3 | 15 | 44 | 59 | 0.000203722 |
| Top-5 | 16 | 41 | 57 | 0.00126356 |
| Top-10 | 15 | 26 | 41 | 0.117275 |

## Tie And Coverage Equivalence Analysis

| Method | Top-score tie cases | Fault-tie cases | Mean maximum tie | Mean fault tie |
|---|---:|---:|---:|---:|
| Original Ochiai | 231 | 256 | 15.87 | 12.05 |
| Branch-aware FL-v1 | 157 | 205 | 11.84 | 6.44 |

Across 6531 executable lines there were only 959 unique line-coverage vectors, an equivalence ratio of 85.32%. Mean maximum class size was 15.24, and mean executable fault-class size was 11.95. Of 625 original tie groups, 510 consisted of one line-coverage class; 220 cases had this pattern at the top score.

## Mechanism Analysis

Average-rank MRR is used for subgroup comparisons so deterministic line-number ordering cannot masquerade as an improvement.

| Dimension | Group | Cases | Original | FL-v1 | Difference | I/U/R |
|---|---|---:|---:|---:|---:|---:|
| Coverage diversity | high (>0.5) | 7 | 0.7545 | 0.7643 | +0.0097 | 1/6/0 |
| Coverage diversity | low (<=0.25) | 245 | 0.2221 | 0.3083 | +0.0863 | 76/60/109 |
| Coverage diversity | medium (0.25-0.5) | 48 | 0.3513 | 0.4744 | +0.1231 | 22/13/13 |
| Fault equivalence class | 1 | 25 | 0.8144 | 0.8211 | +0.0067 | 1/24/0 |
| Fault equivalence class | 2-5 | 58 | 0.4526 | 0.5505 | +0.0980 | 20/22/16 |
| Fault equivalence class | 6-10 | 70 | 0.2195 | 0.3698 | +0.1503 | 34/6/30 |
| Fault equivalence class | >10 | 127 | 0.1148 | 0.1994 | +0.0846 | 44/7/76 |
| Fault equivalence class | non-executable | 20 | 0.0000 | 0.0000 | +0.0000 | 0/20/0 |
| PASS tests | 0 PASS | 52 | 0.2131 | 0.2442 | +0.0310 | 8/10/34 |
| PASS tests | >=1 PASS | 248 | 0.2640 | 0.3668 | +0.1028 | 91/69/88 |
| Repair tests | 1-2 | 35 | 0.1790 | 0.2719 | +0.0929 | 8/7/20 |
| Repair tests | 3-5 | 239 | 0.2679 | 0.3569 | +0.0890 | 79/67/93 |
| Repair tests | 6+ | 26 | 0.2412 | 0.3408 | +0.0996 | 12/5/9 |

## Failure Boundaries

- 0-PASS: 52/300 cases. Their separate result appears in the PASS-test subgroup above.
- Non-executable ground truth: 20/300 (6.67%). These lines cannot receive an SBFL rank.
- Straight-line ambiguity: 205/300 (68.33%). The fault remains tied with a non-fault line that has the same line vector and final branch-aware score.

## Case Studies

### Improved: `7-B-bug-11565651-11565672`

- Tests: 1 PASS / 1 FAIL; fault line(s): L50: `if(st==0 && x==0)`.
- Original: deterministic rank 33, tie interval [1, 42], line score 0.7071, branch score n/a, spectrum (ef=1, ep=1, nf=0, np=0).
- Branch-aware: deterministic rank 1, tie interval [1, 1], line score 0.7071, branch score 1.0000, spectrum (ef=1, ep=1, nf=0, np=0).
- Interpretation: Branch evidence separates the fault from lines with the same line-level Ochiai score and moves it toward the front of that tie.

### Improved: `294-A-bug-10574686-10574699`

- Tests: 2 PASS / 1 FAIL; fault line(s): L19: `if(x!=s-1){`.
- Original: deterministic rank 11, tie interval [1, 16], line score 0.5774, branch score n/a, spectrum (ef=1, ep=2, nf=0, np=0).
- Branch-aware: deterministic rank 1, tie interval [1, 1], line score 0.5774, branch score 1.0000, spectrum (ef=1, ep=2, nf=0, np=0).
- Interpretation: Branch evidence separates the fault from lines with the same line-level Ochiai score and moves it toward the front of that tie.

### Unchanged: `490-C-bug-9623374-9623441`

- Tests: 3 PASS / 1 FAIL; fault line(s): L4: `int modb[1100000],tens[1100000];`.
- Original: fault line is not executable and has no rank.
- Branch-aware: fault line is not executable and has no rank.
- Interpretation: The diff points to a non-executable line, so neither line coverage nor branch evidence can assign it a spectrum or rank.

### Unchanged: `171-B-bug-1996186-1996190`

- Tests: 1 PASS / 1 FAIL; fault line(s): L8: `printf("%d\n", 1 + 12 * (n - 1));`.
- Original: deterministic rank 3, tie interval [1, 4], line score 0.7071, branch score n/a, spectrum (ef=1, ep=1, nf=0, np=0).
- Branch-aware: deterministic rank 3, tie interval [1, 4], line score 0.7071, branch score 0.0000, spectrum (ef=1, ep=1, nf=0, np=0).
- Interpretation: The fault retains an indistinguishable final score; identical execution evidence leaves the original ambiguity unresolved.

### Regressed: `448-B-bug-10250808-10250838`

- Tests: 4 PASS / 1 FAIL; fault line(s): L34: `k++;`.
- Original: deterministic rank 1, tie interval [1, 4], line score 0.7071, branch score n/a, spectrum (ef=1, ep=1, nf=0, np=3).
- Branch-aware: deterministic rank 4, tie interval [4, 4], line score 0.7071, branch score 0.0000, spectrum (ef=1, ep=1, nf=0, np=3).
- Interpretation: A competing branch-bearing line receives stronger branch evidence inside the same line-score group, pushing the fault backward.

### Regressed: `2-C-bug-17380010-17380021`

- Tests: 0 PASS / 2 FAIL; fault line(s): L17: `scanf("%d%d%d",p[i][0],p[i][1],r[i]);`.
- Original: deterministic rank 3, tie interval [1, 3], line score 1.0000, branch score n/a, spectrum (ef=2, ep=0, nf=0, np=0).
- Branch-aware: deterministic rank 3, tie interval [2, 3], line score 1.0000, branch score 0.0000, spectrum (ef=2, ep=0, nf=0, np=0).
- Interpretation: A competing branch-bearing line receives stronger branch evidence inside the same line-score group, pushing the fault backward.

## Research Questions

### RQ1: Does branch-aware FL improve localization accuracy independently?

Yes at the aggregate level. Deterministic MRR rises by +0.0702 and average-rank MRR by +0.0904; both paired bootstrap intervals exclude zero. Top-1, Top-3, and Top-5 improvements are significant under exact McNemar tests, while Top-10 is not. Per-case average-rank outcomes remain mixed (99/79/122).

### RQ2: Does branch evidence reduce coverage-induced ties?

Yes. Top-score tie cases fall from 231 to 157, mean maximum tie size from 15.87 to 11.84, and mean fault-tie size from 12.05 to 6.44. The high equivalence ratio confirms that line coverage information loss is the dominant source of the original ties.

### RQ3: When is branch evidence most useful?

The largest observed average-rank MRR gain occurs for executable fault-equivalence classes of 6-10 lines (+0.1503) and medium coverage diversity (+0.1231). Cases with at least one PASS test gain +0.1028, compared with only +0.0310 for 0-PASS cases. This supports the mechanism: branch evidence helps most when a substantial line-score tie exists and branch outcomes provide usable contrast; it cannot create information when branch spectra are identical or absent. These groups are descriptive, fixed before measurement, and were not used for tuning.

### RQ4: What are the main failure modes of FL-v1?

The main boundaries are non-executable diff lines, persistent straight-line equivalence, and weak spectra in 0-PASS cases. Regression can also occur when a non-fault control-flow line has stronger failing-correlated branch evidence than the true statement. Phase 6 quantifies these boundaries without modifying `fl-v1`.
