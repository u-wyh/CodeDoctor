# Phase 9: Patch Validation Strength and Overfitting

## 1. Research Questions

- **RQ1:** How many V1 plausible patches are rejected by existing hidden validation?
- **RQ2:** How many V2 validated patches exhibit sanitizer-detectable failures?
- **RQ3:** How many V2 validated patches diverge on reference-accepted differential stress inputs?
- **RQ4:** How do the frozen Phase 7/8 rates change under stronger validation?

Phase 9 made **0 LLM calls** and did not repair any rejected patch.

## 2. Formal Patch Corpus

The corpus contains 245 extracted patches from 141 unique cases. The corpus manifest hash is `365902f86f92987d25d5ba9c8167a21b776c57b83ee7025a4ecd11a055eeffd9`. Invalid or missing model outputs remain in the frozen upstream denominators but are not treated as executable patches.

## 3. Validation Ladder

`V0 compile -> V1 repair-time validation -> V2 existing hidden validation -> V3 ASan+UBSan -> V4 reference-based differential validation`.

A **Strongly Validated Patch** is exactly `V2 PASS AND V3 PASS AND V4 PASS`. `V4=N/A` is never strong.

## 4. Existing Plausible / Validated Definitions

V1 uses each frozen experiment's repair-time test result. V2 uses the existing evaluation-only hidden partition. Neither definition is changed post hoc.

## 5. Sanitizer Protocol

V3 compiles C99 sources with ASan+UBSan, frame pointers, and non-PIE settings. Only official tests on which the reference is sanitizer-clean are eligible. Every run retains the 5 s timeout and Docker's 1 CPU, 256 MB, and 64 PID bounds.

## 6. Differential Test Generation

Deterministic Numeric Mutation v1 uses seed `20260820`, signed whitespace-delimited integers, values `{0, 1, -1, x-1, x+1}`, SHA-256 ordering, a 500 proposal cap, and a 100 acceptance cap per case.

It proposed 50,911 candidates and froze 11,983 reference-accepted differential stress inputs. 13 cases have no accepted differential input.

## 7. Reference Acceptance Filter

An input is accepted only when two normal reference runs both exit zero, do not time out, produce identical stdout, and the sanitizer reference run is clean. These are reference-accepted stress inputs, not asserted formally valid inputs.

Reference official-test exclusions: ASan=71, UBSan=44, timeout=11.

## 8. Reproducibility

- Protocol file SHA-256: `4bb2e039216386d9d9baccbaf52793c4b49f061b6c9b6367fe3870f9e8d79656`
- Patch corpus manifest: `365902f86f92987d25d5ba9c8167a21b776c57b83ee7025a4ecd11a055eeffd9`
- Differential manifest: `f593f20b0af854a63d7b8ca3caf41a6734080b1fd7f0cad5fc5e82e0886a7682`
- Result manifest: `48341fd5925b381124bb3cca3e93b3d1f59ff092dcc298edf933761ee34b5e38`

The same case shares one frozen differential set across all arms. Generated input text remains in ignored local checkpoints and is absent from committed manifests.

## 9. Main Results

| Transition | Count | Rate |
|---|---:|---:|
| V1 plausible | 229 | 93.5% of extracted patches |
| V1 -> V2 rejected | 11 | 4.8% of V1 |
| V2 existing validated | 218 | 89.0% of extracted patches |
| V2 -> V3 rejected | 0 | 0.0% of V2 |
| V2 -> V4 rejected | 52 | 25.9% of V4-applicable V2 |
| Strongly validated | 149 | 60.8% of extracted patches |

## 10. Additional Rejection Rate

The pre-registered rate is **52/217 = 24.0%**. The denominator contains V2 patches with at least one applicable stronger validation. Separately, 17 V2 patches have insufficient differential evidence.

## 11. Phase 7 Strong Validation Audit

The original Phase 7 values remain frozen; strong results are a post-hoc audit.

| Arm | Original V2 | Strong | Extracted patches |
|---|---:|---:|---:|
| A | 40/50 (80.0%) | 28/50 (56.0%) | 46 |
| B | 39/50 (78.0%) | 28/50 (56.0%) | 47 |
| C | 46/50 (92.0%) | 35/50 (70.0%) | 50 |

## 12. Phase 8 Strong Validation Audit

| Arm | Original V2 | Strong | Extracted patches |
|---|---:|---:|---:|
| Initial | 85/100 (85.0%) | 55/100 (55.0%) | 91 |
| R | 4/6 (66.7%) | 2/6 (33.3%) | 6 |
| F | 4/6 (66.7%) | 1/6 (16.7%) | 5 |

The Stage 2 denominator remains six per arm; one F response had no executable patch.

## 13. Failure Modes

Affected patches: ASan=0, UBSan=0, differential mismatch=50, runtime error=0, timeout=2.

Finding instances: mismatch=1,697, runtime error=0, timeout=2. A patch may contribute multiple findings but has one deterministic primary failure.

## 14. Case Studies

### V3 sanitizer cases

No V2-passing patch failed V3; no V3 case was selected.

### V4 differential cases

#### `110-C-bug-11176379-11176427`

- Patch: `phase8-stage1/110-C-bug-11176379-11176427/Initial`.
- Buggy behavior: the frozen Codeflaws buggy revision failed its benchmark tests; Phase 9 does not infer a broader formal specification.
- Patch change: 55 changed diff lines; bounded excerpt:

```diff
-//Lucky sum of digits
-
-int num,rem =1,quo1 = 0,quo2=0,i,n;
-scanf("%d",&num);
-if(num == 4 || num == 7)
-printf("%d",num);
```

- Why existing hidden tests missed it: this patch passed every frozen V2 test, while the failing differential observation lies outside that finite partition.
- Stronger evidence: `differential_output_mismatch` on `phase9_differential_0000`; actual output hash `ee3aa64bb94a50845d5024cd4bd20202a4567aed5cd5328c0d97e9920775fc28`, reference output hash `1bad6b8cf97131fceab8543e81f7757195fbb1d36b376ee994ad1cf17699c464` (46 finding(s) total).

#### `141-B-bug-9726688-9726780`

- Patch: `phase7/141-B-bug-9726688-9726780/A`.
- Buggy behavior: the frozen Codeflaws buggy revision failed its benchmark tests; Phase 9 does not infer a broader formal specification.
- Patch change: 4 changed diff lines; bounded excerpt:

```diff
-    else if((((y/s)%2==0))&&((x>0)&&(x<s)))
+    else if((((y/s)%2==0))&&(y>s)&&((x>0)&&(x<s)))
-    else if((((y/s)%2==0))&&((x<0)&&(x>-(s))))
+    else if((((y/s)%2==0))&&(y>s)&&((x<0)&&(x>-(s))))
```

- Why existing hidden tests missed it: this patch passed every frozen V2 test, while the failing differential observation lies outside that finite partition.
- Stronger evidence: `differential_output_mismatch` on `phase9_differential_0016`; actual output hash `ee3aa64bb94a50845d5024cd4bd20202a4567aed5cd5328c0d97e9920775fc28`, reference output hash `53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3` (6 finding(s) total).

#### `143-A-bug-11615524-11615545`

- Patch: `phase8-stage1/143-A-bug-11615524-11615545/Initial`.
- Buggy behavior: the frozen Codeflaws buggy revision failed its benchmark tests; Phase 9 does not infer a broader formal specification.
- Patch change: 15 changed diff lines; bounded excerpt:

```diff
-    long long a,b,c,d,ar[5],j=0,i;
+    long long a,b,c,d;
+    if ((c1+s1-r2)%2 != 0 || (c2+s2-r2)%2 != 0) {
+        printf("-1\n");
+        return 0;
+    }
```

- Why existing hidden tests missed it: this patch passed every frozen V2 test, while the failing differential observation lies outside that finite partition.
- Stronger evidence: `differential_output_mismatch` on `phase9_differential_0001`; actual output hash `ee3aa64bb94a50845d5024cd4bd20202a4567aed5cd5328c0d97e9920775fc28`, reference output hash `d7fee9262c86faf35829b7b11782229670adc02e0397b5cf87bfd73fdc2a03f1` (20 finding(s) total).


## 15. Computational Cost

Phase 9 recorded 86,872 program executions: reference normal=35,058, reference sanitizer=23,902, patch sanitizer=9,142, and patch differential=18,770. Summed batch wall time was 2773.9 s (46.2 min), excluding Python aggregation and regression tests.

## 16. Threats to Validity

- Reference-accepted input does not imply a formally valid problem input.
- Numeric mutation has limited input-space and semantic coverage.
- Differential tests are finite and cannot establish equivalence.
- Sanitizer coverage is incomplete and depends on executed paths.
- Codeflaws may not represent other defects, programs, or repair systems.
- Multiple patches from the same case are statistically dependent.
- V4=N/A conservatively prevents a strong label but does not prove failure.
- Strong validation provides additional empirical evidence, not formal correctness.

## 17. Conclusion

RQ1: hidden validation rejected 11/229 plausible patches. RQ2: V3 rejected 0 V2 patches. RQ3: V4 rejected 52 of 201 V4-applicable V2 patches. RQ4: only 149 extracted patches survived the full ladder, and every frozen Phase 7/8 arm has a lower strong rate than its original V2 rate. Validated Patch and Strongly Validated Patch both remain empirical labels, not formal correctness.
