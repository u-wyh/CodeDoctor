# Branch-Aware Fault Localization on the Codeflaws Pilot

## Research Question

Does real branch-outcome execution evidence reduce the ambiguity of line-level SBFL? This experiment uses the same 50 buggy programs and 180 repair tests as Phase 4. Reference programs, validation tests, and diff ground truth are excluded from collection and ranking; diff ground truth enters only this evaluation.

## Why Phase 4 Produced Ties

Across 1033 executable line records, only 143 distinct per-case line coverage vectors exist. A case has 2.86 unique vectors and 2.70 unique `(ef, ep, nf, np)` patterns on average. Its largest equivalence class averages 14.40 lines and reaches 49 lines. The 58 executable fault lines belong to classes of 10.90 lines on average.

Of 106 original Ochiai tie groups, 92 (86.79%) consist entirely of one coverage equivalence class. In 47 cases the complete highest-score tie is one class. Thus most ambiguity is already present in the line coverage vectors; the Ochiai formula also merges some distinct vectors that have equal `(ef, ep, nf, np)` counts.

Ten cases have no passing repair test, and many cases have only a handful of repair tests. Co-executed statements therefore receive identical vectors, especially along straight-line regions near the fault.

## Method

GCC 12.2/gcov emits each source line's branch arcs under `--branch-probabilities --branch-counts`. Every repair test runs from a clean `.gcno` workspace, so the saved count and taken state are test-local. The experiment observes 796 per-case branch outcomes and 202 branch coverage vectors (4.04 unique vectors per case on average). Each branch outcome receives an `(ef, ep, nf, np)` spectrum and Ochiai score. A source line's branch evidence is the maximum score among its outcomes.

The branch-aware method sorts lexicographically by `(line Ochiai, max branch Ochiai)`. Branch evidence therefore breaks only exact line-score ties and cannot reverse an ordering established by line Ochiai. No parameter is trained on Pilot ground truth.

## Deterministic Metrics

| Method | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original line Ochiai | 10.00% | 32.00% | 46.00% | 62.00% | 0.2601 |
| Line Ochiai + branch tie-breaking | 22.00% | 42.00% | 56.00% | 76.00% | 0.3837 |

## Tie-Aware Metrics

Optimistic uses a tie's best rank, pessimistic its worst rank, and average-rank uses the interval midpoint. These expose uncertainty hidden by line-number ordering.

| Method | Tie policy | Top-1 | Top-3 | Top-5 | Top-10 | MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original line Ochiai | optimistic | 74.00% | 80.00% | 86.00% | 92.00% | 0.7866 |
| Original line Ochiai | pessimistic | 0.00% | 14.00% | 26.00% | 44.00% | 0.1385 |
| Original line Ochiai | average rank | 0.00% | 26.00% | 42.00% | 70.00% | 0.2183 |
| Line Ochiai + branch tie-breaking | optimistic | 44.00% | 62.00% | 70.00% | 88.00% | 0.5623 |
| Line Ochiai + branch tie-breaking | pessimistic | 10.00% | 34.00% | 40.00% | 68.00% | 0.2788 |
| Line Ochiai + branch tie-breaking | average rank | 10.00% | 36.00% | 58.00% | 76.00% | 0.3469 |

## Ambiguity

| Method | Top-score tie cases | Avg unique score keys | Avg score-group size | Avg maximum tie | Tied-fault cases | Avg fault tie |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original line Ochiai | 48 | 2.40 | 9.47 | 15.08 | 47 | 11.87 |
| Line Ochiai + branch tie-breaking | 34 | 4.54 | 5.02 | 10.94 | 41 | 5.77 |

Branch tie-breaking improves average tie-aware fault rank in 25 cases and regresses it in 17 cases. A reduction in generic tie counts does not automatically imply better fault ranking: branch evidence may distinguish nonfaulty lines first or may be absent on the changed statement.

The average-rank policy is the most useful central estimate here: its MRR rises from 0.2183 to 0.3469, while pessimistic MRR rises from 0.1385 to 0.2788. Optimistic MRR falls from 0.7866 to 0.5623: splitting a broad tie removes the unearned assumption that its fault can always occupy the best slot. The deterministic Top-K and MRR gains are therefore accompanied by stronger average and worst-case tie-aware results, not merely a favorable line-number order.

## Cases Where Branch Evidence Helps

### `158-C-bug-9967801-9967822`

Repair-test verdicts: `p1`=PASS, `p2`=PASS, `n1`=FAIL.

```c
  28
  29   			d=getchar();
  30 * 			if(d==47) d=getchar();
  31
  32   			while(d!='\n' && d!=EOF)
```

`*` marks evaluation-only diff ground truth. The line vector follows the repair-test order shown above.

| Fault | Line | Line coverage vector | Line Ochiai | Max branch Ochiai | Original rank | Branch-aware rank |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
|  | L3 | `111` | 0.5774 | 0.0000 | 1 | 13 |
|  | L5 | `111` | 0.5774 | 0.0000 | 2 | 14 |
|  | L9 | `111` | 0.5774 | 0.0000 | 3 | 15 |
|  | L10 | `111` | 0.5774 | 0.0000 | 4 | 16 |
|  | L12 | `111` | 0.5774 | 0.0000 | 5 | 17 |
|  | L13 | `111` | 0.5774 | 0.0000 | 6 | 18 |
|  | L15 | `111` | 0.5774 | 0.5774 | 7 | 1 |
|  | L18 | `111` | 0.5774 | 0.0000 | 8 | 19 |
|  | L20 | `111` | 0.5774 | 0.5774 | 9 | 2 |
|  | L22 | `111` | 0.5774 | 0.0000 | 10 | 20 |
|  | L23 | `111` | 0.5774 | 0.0000 | 11 | 21 |
|  | L25 | `111` | 0.5774 | 0.0000 | 12 | 22 |
|  | L29 | `111` | 0.5774 | 0.0000 | 13 | 23 |
| yes | L30 | `111` | 0.5774 | 0.5774 | 14 | 3 |
|  | L32 | `111` | 0.5774 | 0.5774 | 15 | 4 |
|  | L34 | `111` | 0.5774 | 0.5774 | 16 | 5 |

| Branch outcome | Taken vector | Execution counts | (ef,ep,nf,np) | Ochiai |
| --- | --- | --- | --- | ---: |
| L15 b0 | `1 1 1` | `7 4 5` | (1,2,0,0) | 0.5774 |
| L15 b1 | `1 1 1` | `1 1 1` | (1,2,0,0) | 0.5774 |
| L20 b0 | `1 1 1` | `3 2 2` | (1,2,0,0) | 0.5774 |
| L20 b1 | `1 1 1` | `4 2 3` | (1,2,0,0) | 0.5774 |
| L30 b0 | `1 1 1` | `1 1 2` | (1,2,0,0) | 0.5774 |
| L30 b1 | `1 1 0` | `2 1 0` | (0,2,1,0) | 0.0000 |
| L32 b0 | `1 1 1` | `24 8 18` | (1,2,0,0) | 0.5774 |
| L32 b1 | `1 1 1` | `3 2 2` | (1,2,0,0) | 0.5774 |
| L32 b2 | `1 1 1` | `24 8 18` | (1,2,0,0) | 0.5774 |
| L32 b3 | `0 0 0` | `0 0 0` | (0,0,1,2) | 0.0000 |
| L34 b0 | `1 1 1` | `3 3 1` | (1,2,0,0) | 0.5774 |
| L34 b1 | `1 1 1` | `21 5 17` | (1,2,0,0) | 0.5774 |
| L34 b2 | `1 1 1` | `2 2 1` | (1,2,0,0) | 0.5774 |
| L34 b3 | `1 1 0` | `1 1 0` | (0,2,1,0) | 0.0000 |

Original fault tie interval: `[1, 44]`; branch-aware interval: `[1, 12]`. The fault's max branch score is 0.5774; it exceeds 32 lines inside the original 44-line tie, so its uncertainty interval contracts. Branch evidence can only separate lines whose branch-outcome spectra differ; lines without branch records or with identical branch vectors remain indistinguishable.

### `450-A-bug-12286209-12286212`

Repair-test verdicts: `n2`=FAIL, `n3`=FAIL, `n1`=FAIL.

```c
  29               counter++;
  30           }
  31 *         if(counter=n-1){
  32               break;
  33           }
```

`*` marks evaluation-only diff ground truth. The line vector follows the repair-test order shown above.

| Fault | Line | Line coverage vector | Line Ochiai | Max branch Ochiai | Original rank | Branch-aware rank |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
|  | L3 | `111` | 1.0000 | 0.0000 | 1 | 8 |
|  | L7 | `111` | 1.0000 | 0.0000 | 2 | 9 |
|  | L10 | `111` | 1.0000 | 0.0000 | 3 | 10 |
|  | L12 | `111` | 1.0000 | 1.0000 | 4 | 1 |
|  | L13 | `111` | 1.0000 | 0.0000 | 5 | 11 |
|  | L16 | `111` | 1.0000 | 0.0000 | 6 | 12 |
|  | L17 | `111` | 1.0000 | 1.0000 | 7 | 2 |
|  | L18 | `111` | 1.0000 | 0.0000 | 8 | 13 |
|  | L20 | `111` | 1.0000 | 0.0000 | 9 | 14 |
|  | L21 | `111` | 1.0000 | 1.0000 | 10 | 3 |
|  | L25 | `111` | 1.0000 | 0.0000 | 11 | 15 |
|  | L26 | `111` | 1.0000 | 0.0000 | 12 | 16 |
|  | L27 | `111` | 1.0000 | 1.0000 | 13 | 4 |
|  | L28 | `111` | 1.0000 | 0.0000 | 14 | 17 |
|  | L29 | `111` | 1.0000 | 0.0000 | 15 | 18 |
| yes | L31 | `111` | 1.0000 | 1.0000 | 16 | 5 |

| Branch outcome | Taken vector | Execution counts | (ef,ep,nf,np) | Ochiai |
| --- | --- | --- | --- | ---: |
| L12 b0 | `1 1 1` | `5 6 5` | (3,0,0,0) | 1.0000 |
| L12 b1 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L17 b0 | `1 1 1` | `5 6 5` | (3,0,0,0) | 1.0000 |
| L17 b1 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L21 b0 | `0 0 0` | `0 0 0` | (0,0,3,0) | 0.0000 |
| L21 b1 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L27 b0 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L27 b1 | `0 0 0` | `0 0 0` | (0,0,3,0) | 0.0000 |
| L27 b2 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L27 b3 | `0 0 0` | `0 0 0` | (0,0,3,0) | 0.0000 |
| L31 b0 | `1 1 1` | `1 1 1` | (3,0,0,0) | 1.0000 |
| L31 b1 | `0 0 0` | `0 0 0` | (0,0,3,0) | 0.0000 |

Original fault tie interval: `[1, 22]`; branch-aware interval: `[1, 7]`. The fault's max branch score is 1.0000; it exceeds 15 lines inside the original 22-line tie, so its uncertainty interval contracts. Branch evidence can only separate lines whose branch-outcome spectra differ; lines without branch records or with identical branch vectors remain indistinguishable.


## Cases Where Branch Evidence Does Not Help

### `471-A-bug-18116605-18116641`

Repair-test verdicts: `p1`=PASS, `p2`=PASS, `p3`=PASS, `n1`=FAIL.

```c
   2
   3   int main(int argc, char *argv[])
   4 * {
   5   	int m[9],i,a,b;
   6
  18
  19   	else
  20 * 	{
  21   		a=0;
  22   		b=0;
```

`*` marks evaluation-only diff ground truth. The line vector follows the repair-test order shown above.

| Fault | Line | Line coverage vector | Line Ochiai | Max branch Ochiai | Original rank | Branch-aware rank |
| --- | ---: | --- | ---: | ---: | ---: | ---: |


| Branch outcome | Taken vector | Execution counts | (ef,ep,nf,np) | Ochiai |
| --- | --- | --- | --- | ---: |
| none | - | - | - | - |

Original fault tie interval: `None`; branch-aware interval: `None`. The diff ground truth has no executable gcov line, so neither line nor branch evidence can rank it. Branch evidence can only separate lines whose branch-outcome spectra differ; lines without branch records or with identical branch vectors remain indistinguishable.

### `192-A-bug-18022160-18022194`

Repair-test verdicts: `p1`=PASS, `p2`=PASS, `n1`=FAIL.

```c
  15           tag=sqrt(triangle2);
  16           if(triangle2==0)
  17 *         {
  18               printf("NO");
  19 *             break;
  20           }
  21           if(tag*tag+tag==triangle2)
```

`*` marks evaluation-only diff ground truth. The line vector follows the repair-test order shown above.

| Fault | Line | Line coverage vector | Line Ochiai | Max branch Ochiai | Original rank | Branch-aware rank |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
|  | L18 | `001` | 1.0000 | 0.0000 | 1 | 1 |
| yes | L19 | `001` | 1.0000 | 0.0000 | 2 | 2 |

| Branch outcome | Taken vector | Execution counts | (ef,ep,nf,np) | Ochiai |
| --- | --- | --- | --- | ---: |
| none | - | - | - | - |

Original fault tie interval: `[1, 2]`; branch-aware interval: `[1, 2]`. The fault line has no failing-correlated branch outcome, so branch evidence cannot lift it inside the original line-score tie. Branch evidence can only separate lines whose branch-outcome spectra differ; lines without branch records or with identical branch vectors remain indistinguishable.


## Meaning for Later Repair

The conservative tie-break produces a more honest candidate order when failing and passing executions choose different branch outcomes inside a line-score tie. It cannot add semantic evidence to straight-line statements, non-executable diff lines, or branch outcomes that all repair tests exercise identically. A later repair component should preserve tie intervals and equivalence-class context instead of treating a deterministic line number as certainty.

## Limitations

This is a single 50-case Pilot under one GCC/gcov version. Repair suites are small, ten cases lack a PASS execution, and textual diff lines are an imperfect fault oracle. Branch arcs are compiler-generated control-flow outcomes rather than source-level predicate truth values, and max aggregation may emphasize one exceptional arc. The experiment tests ambiguity reduction, not causal fault identification or cross-dataset generalization.
