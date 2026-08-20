# Table Validation Main

| section | label | numerator | denominator | rate | existing_v2 | strong | absolute_drop | relative_survival | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| corpus | Formal patches | 245 |  |  |  |  |  |  | 141 unique cases |
| ladder | V1 Plausible | 229 | 245 | 93.47% |  |  |  |  | repair-time validation |
| ladder | V2 Existing Validated | 218 | 245 | 88.98% |  |  |  |  | hidden validation |
| ladder | V3 Sanitizer-Clean | 217 | 217 | 100.00% |  |  |  |  | 1 V2 patch had V3 N/A |
| ladder | V4 Differential Survivor | 149 | 201 | 74.13% |  |  |  |  | 52 rejected; 17 V2 patches V4 N/A |
| ladder | Strongly Validated | 149 | 245 | 60.82% |  |  |  |  | V2 PASS and V3 PASS and V4 PASS |
| sanitizer audit | ASan patch rejection | 0 | 218 | 0.00% |  |  |  |  | frozen Phase 9 report |
| sanitizer audit | UBSan patch rejection | 0 | 218 | 0.00% |  |  |  |  | frozen Phase 9 report |
| differential audit | Candidates | 50911 |  |  |  |  |  |  | generated stress inputs |
| differential audit | Reference-accepted stress inputs | 11983 | 50911 | 23.54% |  |  |  |  | 13 cases had zero accepted tests |
| differential audit | Output-mismatch patches | 50 | 201 | 24.88% |  |  |  |  | 1697 findings |
| differential audit | Timeout patches | 2 | 201 | 1.00% |  |  |  |  |  |
| differential audit | Runtime-error patches | 0 | 201 | 0.00% |  |  |  |  |  |
| differential audit | Additional rejection | 52 | 217 | 23.96% |  |  |  |  | V2 patches with V3/V4 applicable |
| arm audit | Phase 7 A |  | 50 |  | 40 | 28 | 24.00% | 70.00% |  |
| arm audit | Phase 7 B |  | 50 |  | 39 | 28 | 22.00% | 71.79% |  |
| arm audit | Phase 7 C |  | 50 |  | 46 | 35 | 22.00% | 76.09% |  |
| arm audit | Phase 8 Initial |  | 100 |  | 85 | 55 | 30.00% | 64.71% |  |
| arm audit | Phase 8 F |  | 6 |  | 4 | 1 | 50.00% | 25.00% | small cohort M=6 |
| arm audit | Phase 8 R |  | 6 |  | 4 | 2 | 33.33% | 50.00% | small cohort M=6 |

Generated deterministically from frozen formal artifacts and reports.
