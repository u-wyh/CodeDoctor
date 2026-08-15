# Branch-Aware Fault Localization

## Motivation

Phase 4 ranked executable source lines with line-level spectra. On the 50-case Codeflaws Pilot, 48 cases had a tie at the highest Ochiai score and 47 had an executable fault line inside a tie. A deterministic line-number order makes these rankings reproducible, but it does not make equally scored lines distinguishable.

Phase 5 asks a narrower question: can real branch-outcome evidence reduce this ambiguity without replacing line-level SBFL?

## Coverage Equivalence Classes

For an executable line `l` and ordered repair tests `t1 ... tn`, its coverage vector is:

```text
v(l) = [covered(l, t1), ..., covered(l, tn)]
```

Lines with the same vector form a coverage equivalence class. No line-level spectrum formula can distinguish members of one class because they produce the same `ef`, `ep`, `nf`, and `np`.

The Pilot contains 1,033 per-case executable line records but only 143 per-case unique vectors. A case has 2.86 vectors on average; its largest class averages 14.40 lines and reaches 49. Executable fault lines belong to classes of 10.90 lines on average. Of 106 original Ochiai tie groups, 92 are entirely one coverage equivalence class. The dominant source of ties is therefore evidence coarseness, although Ochiai can also assign one score to distinct vectors with equal spectrum counts.

Small repair suites encourage this collapse. Ten cases have no passing test, and many statements in one straight-line region always execute together. A formula change cannot recover distinctions that the coverage matrix does not contain.

## Real Branch Evidence

The collector invokes GCC 12.2 gcov with:

```text
gcov --json-format --branch-probabilities --branch-counts source.c
```

For every repair test, it records each compiler branch arc as:

```text
source line, branch index, execution count, taken, fallthrough, throw
```

Branch index is the stable position of an arc in that source line's gcov JSON branch list. `taken` means its execution count is greater than zero. Each test starts from a copied executable and clean `.gcno` in a new temporary directory and constrained Docker container, so `.gcda` from one test cannot affect another.

The branch records are compiler control-flow arcs. They should not be described as a perfect source-level predicate model: short-circuit expressions, loop arcs, and compiler-generated paths can produce several outcomes on one line.

## Branch Spectrum

Each `(line, branch index)` is treated as a binary outcome: taken or not taken by a repair test. PASS and FAIL verdicts build the same four counts used for lines:

```text
ef = failing tests taking the outcome
ep = passing tests taking the outcome
nf = failing tests not taking the outcome
np = passing tests not taking the outcome
```

The first branch suspiciousness formula is Ochiai:

```text
ef / sqrt((ef + nf) * (ef + ep))
```

For source-level presentation, branch evidence on a line is the maximum score among its branch outcomes. Max aggregation preserves one highly failure-correlated control outcome instead of diluting it with unrelated arcs on the same line. It may also overemphasize an exceptional arc, so this remains an explicit experimental choice.

## Conservative Tie-Breaking

The branch-aware ranking key is:

```text
(-line_ochiai, -max_branch_ochiai, source_line)
```

Branch evidence is consulted only when two lines have exactly the same line Ochiai. It cannot reverse an ordering already established by the line spectrum. This lexicographic rule has no trained parameter and uses no Pilot ground truth during localization.

The experiment deliberately does not select a weighted-fusion alpha. An alpha sweep on the same Pilot ground truth would be exploratory tuning rather than independent evidence of generalization.

## Tie-Aware Metrics

For a fault in a tie interval `[a, b]`:

```text
best rank    = a
worst rank   = b
average rank = (a + b) / 2
tie size     = b - a + 1
```

Top-K is reported under optimistic (`best <= K`), pessimistic (`worst <= K`), and average-rank (`average <= K`) policies. MRR uses the reciprocal of the corresponding rank. For multiple fault lines, the first reachable fault uses the earliest available interval boundary.

These views are necessary because deterministic line-number Top-K can reward or punish a fault arbitrarily inside a tie. Optimistic metrics can also be misleadingly high when ties are huge: splitting a tie may lower optimistic MRR while improving average and pessimistic MRR.

## Pilot Findings

Branch evidence increases the average number of ranking score keys per case from 2.40 to 4.54. Highest-score tie cases fall from 48 to 34, average maximum tie size from 15.08 to 10.94, and average executable-fault tie size from 11.87 to 5.77.

Original line Ochiai has deterministic Top-1/3/5/10 of 10%/32%/46%/62% and MRR 0.2601. Branch tie-breaking reaches 22%/42%/56%/76% and MRR 0.3837. Average-rank MRR increases from 0.2183 to 0.3469, and pessimistic MRR from 0.1385 to 0.2788. Branch evidence improves average fault rank in 25 cases and regresses it in 17; it is useful but not uniformly correct.

The complete generated analysis, including two improved and two unimproved cases, is in `benchmark/reports/fault_localization_branch_report.md`.

## Leakage Boundary

Localization inputs remain limited to buggy source, repair inputs, repair expected outputs, verdicts, and runtime coverage. Reference source, validation tests, and textual diff ground truth are absent from coverage, spectra, branch scores, and rankings. Ground truth is loaded only by evaluation and report generation.

## Limitations

- The study has 50 C cases, one compiler version, and small repair suites.
- Ten cases lack successful-execution contrast.
- Textual diff lines are an imperfect fault oracle and some are not executable.
- Branch arcs do not provide semantic causality and straight-line faults have no local branch evidence.
- Max aggregation and the Pilot itself require evaluation on broader, independently selected data before generalization claims.
