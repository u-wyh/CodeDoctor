"""Deterministic suspicious-line ranking with explicit tie boundaries."""

from .algorithms import SuspiciousnessFormula
from .models import RankedLine, SpectrumLine


def _source_snippet(source_lines: list[str], line: int) -> str:
    return (
        source_lines[line - 1].strip()
        if 0 < line <= len(source_lines)
        else ""
    )


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
        snippet = _source_snippet(source_lines, item.line)
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


def rank_with_branch_tiebreak(
    spectrum: tuple[SpectrumLine, ...],
    formula: SuspiciousnessFormula,
    branch_scores: dict[int, float],
    source: str,
) -> tuple[RankedLine, ...]:
    """Use branch evidence only inside exact line-score tie groups."""

    source_lines = source.splitlines()
    scored = sorted(
        (
            (formula(item), branch_scores.get(item.line, 0.0), item)
            for item in spectrum
        ),
        key=lambda value: (-value[0], -value[1], value[2].line),
    )
    tie_bounds: dict[tuple[float, float], tuple[int, int]] = {}
    for position, (line_score, branch_score, _) in enumerate(scored, start=1):
        key = (line_score, branch_score)
        start, _ = tie_bounds.get(key, (position, position))
        tie_bounds[key] = (start, position)

    rankings = []
    for rank, (line_score, branch_score, item) in enumerate(scored, start=1):
        tie_start, tie_end = tie_bounds[(line_score, branch_score)]
        rankings.append(
            RankedLine(
                rank=rank,
                line=item.line,
                score=line_score,
                ef=item.ef,
                ep=item.ep,
                nf=item.nf,
                np=item.np,
                source_snippet=_source_snippet(source_lines, item.line),
                tie_start_rank=tie_start,
                tie_end_rank=tie_end,
                branch_score=branch_score,
            )
        )
    return tuple(rankings)
