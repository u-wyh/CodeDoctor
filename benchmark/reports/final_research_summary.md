# CodeDoctor Final Research Summary

## 1. Research Scope

CodeDoctor's frozen research pipeline is: buggy C/C++ program -> repair tests and coverage -> fault localization -> LLM repair -> execution feedback -> patch validation -> benchmark evaluation. The four research parts are fault localization (Phases 4-6), repair evidence (Phase 7), execution feedback (Phase 8), and validation strength (Phase 9). No fifth core direction is introduced.

## 2. Experimental Datasets

The formal datasets contain 50 FL Pilot, 300 independent FL evaluation, 50 Phase 7 repair, and 100 Phase 8 repair cases. Their six pairwise overlaps are all zero. Dataset manifest identities and the full overlap matrix are frozen in `benchmark/metadata/final/dataset_overlap_matrix.json`.

## 3. RQ1 - Fault Localization

On the independent 300-case evaluation, deterministic MRR increased from 0.2773 to 0.3475; average-rank MRR increased from 0.2552 to 0.3456. Top-score ties fell from 231 to 157 and fault ties from 256 to 205. Coverage equivalence is associated with many line-level ties, and branch evidence can break some of them. Not every case improves: average-rank outcomes were 99 improved, 79 unchanged, and 122 regressed. Boundaries include non-executable faults, straight-line ambiguity, weak 0-PASS spectra, and misleading branch evidence.

## 4. RQ2 - Repair-Time Evidence

Phase 7 validated A=40/50, B=39/50, and C=46/50. FL-v1 alone did not improve B over A (-2 percentage points). Adding frozen runtime evidence on top of FL-v1 was associated with a +14-point paired difference for C versus B, with 8 improvements and 1 regression. This is one stochastic 50-case, single-model run with finite validation and unadjusted multiple comparisons, not a general causal proof.

## 5. RQ3 - Execution Feedback

A second repair opportunity rescued some first-round failures. In the frozen M=6 paired cohort, R and F both validated 4/6: both success=3, R fail/F success=1, R success/F fail=1, both fail=1. The difference is zero, bootstrap CI [-0.5, +0.5], and exact McNemar p=1.0. This is paired case-level evidence and does not establish an aggregate feedback advantage.

## 6. RQ4 - Patch Validation Strength

The formal corpus contains 245 patches from 141 cases. V1 plausible=229, V2 existing validated=218, and strongly validated=149. V3 produced no patch rejection. Among 201 V4-applicable V2 patches, 52 (25.9%) were rejected by reference-based differential stress testing. Strongly Validated Patch is not Formally Correct Patch.

## 7. Cross-Phase Findings

1. Coverage equivalence contributes to SBFL ties, and branch evidence reduces some ties.
2. Better localization metrics do not automatically yield better LLM repair utility: FL-v1 improved Phase 6 localization, while Phase 7 B did not outperform A.
3. Runtime evidence showed stronger repair utility than static FL evidence in this frozen run: B=78% and C=92%, with cautious associative wording.
4. Validation strength changes apparent success substantially: Phase 7 C falls from 92% V2 to 70% strong, and Phase 8 Initial from 85% V2 to 55% strong.

## 8. Reproducibility

The final formal experiment registry hash is `e2f7728ffce144dda076fc991c5812246d5416c4f2af6ac196f203472f463fef` and the reproducibility registry hash is `1d4ee7faa486ad4ac16dd9e59f5505dcaf1334d1c2e7b8b102c6eb5b81a3063b`. All registered frozen hashes and zero-diff checks passed. Raw large experiments were not rerun.

## 9. Cost

Formal LLM experiments attempted 262 calls, received 260 responses, used 2,596,824 provider-reported tokens, and have an estimated usage cost of `$0.54485862`. This is not a billing export. Final consolidation made zero LLM calls and cost `$0`.

## 10. Threats to Validity

- Internal: LLM stochasticity, single-attempt protocols, provider failures, length truncation, and finite tests.
- Construct: FL metrics are not repair utility; Validated and Strongly Validated do not mean Correct; reference-accepted stress inputs are not formally valid inputs.
- External: Codeflaws, competitive-programming C/C++ defects, and one LLM family/model limit generalization.
- Statistical: Phase 7 n=50, Phase 8 R/F n=6, dependent same-case patches, post-hoc subgroups, and multiple comparisons.

## 11. Final Conclusions

The frozen evidence supports four bounded contributions: empirical analysis of coverage-equivalence ties and branch tie-breaking; a strict-information-boundary repair evidence ablation; a paired design separating second-chance and feedback effects; and a validation ladder showing that hidden-test validation can overstate patch reliability. It does not support state-of-the-art, universal-superiority, or formal-correctness claims.
