# Table Fl Main

| experiment | method | cases | top_1 | top_3 | top_5 | top_10 | mrr | average_rank_mrr | pessimistic_mrr | top_score_tie_cases | fault_line_tie_cases | average_max_tie_size | average_fault_tie_size | deterministic_mrr_delta | deterministic_mrr_ci_95 | average_rank_mrr_delta | average_rank_mrr_ci_95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phase 4 FL Pilot | Original line Ochiai | 50 | 10.00% | 32.00% | 46.00% | 62.00% | 0.260146 | 0.218321 | 0.138497 | 48 | 47 | 15.08 | 11.87234 |  |  |  |  |
| Phase 5 FL-v1 Pilot | Branch-aware FL-v1 | 50 | 22.00% | 42.00% | 56.00% | 76.00% | 0.383671 | 0.346875 | 0.278824 | 34 | 41 | 10.94 | 5.765957 |  |  |  |  |
| Phase 6 Independent | Original line Ochiai | 300 | 12.33% | 30.33% | 44.00% | 68.67% | 0.277261 | 0.255187 | 0.187952 | 231 | 256 | 15.866667 | 12.046429 |  |  |  |  |
| Phase 6 Independent | Branch-aware FL-v1 | 300 | 18.33% | 40.00% | 52.33% | 72.33% | 0.347476 | 0.345552 | 0.30044 | 157 | 205 | 11.843333 | 6.435714 | 0.070215 | [0.043154140501772936, 0.09862142349631034] | 0.090365 | [0.06709788792517683, 0.11558144149447525] |

Generated deterministically from frozen formal artifacts and reports.
