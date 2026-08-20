# Table Repair Main

| arm | context | cases | valid_output | compile_success | plausible | validated | validated_rate | paired_comparison | paired_improved | paired_regressed | paired_difference | bootstrap_95_lower | bootstrap_95_upper | mcnemar_p | secondary_paired_comparison | secondary_paired_improved | secondary_paired_regressed | secondary_paired_difference | secondary_bootstrap_95_lower | secondary_bootstrap_95_upper | secondary_mcnemar_p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Base Context | 50 | 46 | 46 | 43 | 40 | 80.00% |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| B | Base + FL-v1 | 50 | 47 | 47 | 42 | 39 | 78.00% | B-A | 5 | 6 | -2.00% | -14.00% | 12.00% | 1 |  |  |  |  |  |  |  |
| C | Base + FL-v1 + Runtime Evidence | 50 | 50 | 50 | 49 | 46 | 92.00% | C-B | 8 | 1 | 14.00% | 4.00% | 26.00% | 0.039062 | C-A | 8 | 2 | 0.12 | 0 | 0.24 | 0.109375 |

Generated deterministically from frozen formal artifacts and reports.
