# Codeflaws Pilot Report

Generated from the current manifest and Docker verification artifacts at `2026-08-15T13:38:20.349208+00:00`.

## Dataset Summary

| Metric | Value |
| --- | ---: |
| Parsed cases | 3904 |
| Statically valid cases | 3884 |
| Statically invalid cases | 20 |
| Dynamic candidates tested | 55 |
| Pilot cases | 50 |
| Excluded records | 25 |

## Reproduction Results

| Metric | Result |
| --- | ---: |
| Buggy compile success | 55 / 55 (100.00%) |
| Reference compile success | 55 / 55 (100.00%) |
| Reproducible cases | 50 / 55 (90.91%) |

A case is reproducible only when both programs compile, the reference passes every repair and validation test, and the buggy program fails at least one test.

## Test Counts Per Pilot Case

| Suite | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: |
| Repair | 2 | 3.0 | 3.6 | 11 |
| Validation | 1 | 27.5 | 32.0 | 90 |
| Total | 3 | 31.0 | 35.6 | 94 |

## Defect Class Distribution

| Defect class | Cases |
| --- | ---: |
| DCCA | 1 |
| DCCR | 2 |
| DMAA | 1 |
| DRAC | 2 |
| DRVA | 2 |
| DRWV | 2 |
| HBRN | 2 |
| HCOM | 2 |
| HDIM | 2 |
| HDMS | 2 |
| HEXP | 2 |
| HIMS | 2 |
| HOTH | 2 |
| OAAN | 1 |
| OAID | 2 |
| OAIS | 1 |
| OEDE | 1 |
| OFFN | 1 |
| OFPF | 1 |
| OFPO | 1 |
| OICD | 1 |
| OILN | 1 |
| OIRO | 1 |
| OITC | 1 |
| OLLN | 1 |
| OMOP | 1 |
| ORRN | 1 |
| SDFN | 1 |
| SDIB | 1 |
| SDIF | 1 |
| SDLA | 1 |
| SIIF | 1 |
| SIRT | 1 |
| SISA | 1 |
| SISF | 1 |
| SMOV | 1 |
| SMVB | 1 |
| STYP | 1 |

## Exclusion Reasons

| Reason | Cases |
| --- | ---: |
| buggy_passed_all_tests | 1 |
| reference_failed_repair_tests | 2 |
| reference_failed_validation_tests | 2 |
| static_validation_failed | 20 |
