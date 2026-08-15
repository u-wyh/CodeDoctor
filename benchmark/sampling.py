"""Deterministic stratified ordering for Codeflaws pilot candidates."""

import random
from collections import defaultdict
from typing import Iterable

from .models import BenchmarkCase


def stratified_case_order(
    cases: Iterable[BenchmarkCase], seed: int
) -> list[BenchmarkCase]:
    """Shuffle within defect classes, then round-robin across classes."""

    groups: dict[str, list[BenchmarkCase]] = defaultdict(list)
    for case in cases:
        groups[str(case.metadata.get("defect_class") or "unknown")].append(case)

    randomizer = random.Random(seed)
    for defect_class in sorted(groups):
        groups[defect_class].sort(key=lambda case: case.case_id)
        randomizer.shuffle(groups[defect_class])

    ordered: list[BenchmarkCase] = []
    classes = sorted(groups)
    offset = 0
    while True:
        added = False
        for defect_class in classes:
            group = groups[defect_class]
            if offset < len(group):
                ordered.append(group[offset])
                added = True
        if not added:
            return ordered
        offset += 1
