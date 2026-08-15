"""Top-K and reciprocal-rank evaluation against evaluation-only fault lines."""

from dataclasses import dataclass

from .models import RankedLine


TOP_K_VALUES = (1, 3, 5, 10)


@dataclass(frozen=True)
class CaseMetric:
    first_fault_rank: int | None
    reciprocal_rank: float
    top_k: dict[int, bool]


def evaluate_case(
    ranking: tuple[RankedLine, ...], fault_lines: tuple[int, ...]
) -> CaseMetric:
    ground_truth = set(fault_lines)
    first = next(
        (item.rank for item in ranking if item.line in ground_truth), None
    )
    return CaseMetric(
        first_fault_rank=first,
        reciprocal_rank=1.0 / first if first is not None else 0.0,
        top_k={k: first is not None and first <= k for k in TOP_K_VALUES},
    )


def aggregate_metrics(metrics: list[CaseMetric]) -> dict[str, float | int]:
    total = len(metrics)
    result: dict[str, float | int] = {"evaluated_cases": total}
    for k in TOP_K_VALUES:
        hits = sum(metric.top_k[k] for metric in metrics)
        result[f"top_{k}_hits"] = hits
        result[f"top_{k}_accuracy"] = hits / total if total else 0.0
    result["mrr"] = (
        sum(metric.reciprocal_rank for metric in metrics) / total
        if total
        else 0.0
    )
    return result
