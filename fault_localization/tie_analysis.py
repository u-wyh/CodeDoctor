"""Coverage-vector equivalence classes and score-tie summaries."""

from dataclasses import dataclass

from .models import CoverageMatrix, RankedLine


@dataclass(frozen=True)
class CoverageEquivalenceClass:
    vector: tuple[int, ...]
    lines: tuple[int, ...]


def coverage_equivalence_classes(
    matrix: CoverageMatrix,
) -> tuple[CoverageEquivalenceClass, ...]:
    groups: dict[tuple[int, ...], list[int]] = {}
    for line in matrix.executable_lines:
        vector = tuple(int(line in test.covered_lines) for test in matrix.tests)
        groups.setdefault(vector, []).append(line)
    return tuple(
        CoverageEquivalenceClass(vector=vector, lines=tuple(lines))
        for vector, lines in sorted(groups.items(), key=lambda item: item[1][0])
    )


def branch_equivalence_classes(
    matrix: CoverageMatrix,
) -> dict[tuple[int, ...], tuple[tuple[int, int], ...]]:
    groups: dict[tuple[int, ...], list[tuple[int, int]]] = {}
    for key in matrix.executable_branches:
        vector = tuple(
            int(
                any(
                    (branch.line, branch.branch_index) == key and branch.taken
                    for branch in test.branches
                )
            )
            for test in matrix.tests
        )
        groups.setdefault(vector, []).append(key)
    return {
        vector: tuple(outcomes)
        for vector, outcomes in sorted(groups.items(), key=lambda item: item[1][0])
    }


def tie_group_sizes(ranking: tuple[RankedLine, ...]) -> tuple[int, ...]:
    groups = {
        (item.tie_start_rank, item.tie_end_rank)
        for item in ranking
    }
    return tuple(sorted(end - start + 1 for start, end in groups))
