"""Deterministic suspicious-line ranking with explicit tie boundaries."""

from .algorithms import SuspiciousnessFormula
from .models import RankedLine, SpectrumLine


def rank_spectrum(
    spectrum: tuple[SpectrumLine, ...],
    formula: SuspiciousnessFormula,
    source: str,
) -> tuple[RankedLine, ...]:
    source_lines = source.splitlines()
    scored = sorted(
        ((formula(item), item) for item in spectrum),
        key=lambda pair: (-pair[0], pair[1].line),
    )
    tie_bounds: dict[float, tuple[int, int]] = {}
    for position, (score, _) in enumerate(scored, start=1):
        start, _ = tie_bounds.get(score, (position, position))
        tie_bounds[score] = (start, position)

    rankings = []
    for rank, (score, item) in enumerate(scored, start=1):
        snippet = (
            source_lines[item.line - 1].strip()
            if 0 < item.line <= len(source_lines)
            else ""
        )
        tie_start, tie_end = tie_bounds[score]
        rankings.append(
            RankedLine(
                rank=rank,
                line=item.line,
                score=score,
                ef=item.ef,
                ep=item.ep,
                nf=item.nf,
                np=item.np,
                source_snippet=snippet,
                tie_start_rank=tie_start,
                tie_end_rank=tie_end,
            )
        )
    return tuple(rankings)
