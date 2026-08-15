"""Top-K and reciprocal-rank evaluation against evaluation-only fault lines."""

from dataclasses import dataclass
from typing import Any

from .models import RankedLine


TOP_K_VALUES = (1, 3, 5, 10)


@dataclass(frozen=True)
class CaseMetric:
    first_fault_rank: int | None
    reciprocal_rank: float
    top_k: dict[int, bool]
    best_fault_rank: int | None
    worst_fault_rank: int | None
    average_fault_rank: float | None
    fault_tie_size: int | None
    optimistic_top_k: dict[int, bool]
    pessimistic_top_k: dict[int, bool]
    average_rank_top_k: dict[int, bool]


def evaluate_case(
    ranking: tuple[RankedLine, ...], fault_lines: tuple[int, ...]
) -> CaseMetric:
    ground_truth = set(fault_lines)
    first = next(
        (item.rank for item in ranking if item.line in ground_truth), None
    )
    fault_entries = tuple(item for item in ranking if item.line in ground_truth)
    best = (
        min(item.tie_start_rank for item in fault_entries)
        if fault_entries
        else None
    )
    worst = (
        min(item.tie_end_rank for item in fault_entries)
        if fault_entries
        else None
    )
    average = (best + worst) / 2 if best is not None and worst is not None else None
    first_group = (
        min(
            fault_entries,
            key=lambda item: (item.tie_start_rank, item.tie_end_rank, item.rank),
        )
        if fault_entries
        else None
    )
    return CaseMetric(
        first_fault_rank=first,
        reciprocal_rank=1.0 / first if first is not None else 0.0,
        top_k={k: first is not None and first <= k for k in TOP_K_VALUES},
        best_fault_rank=best,
        worst_fault_rank=worst,
        average_fault_rank=average,
        fault_tie_size=(
            first_group.tie_end_rank - first_group.tie_start_rank + 1
            if first_group is not None
            else None
        ),
        optimistic_top_k={k: best is not None and best <= k for k in TOP_K_VALUES},
        pessimistic_top_k={
            k: worst is not None and worst <= k for k in TOP_K_VALUES
        },
        average_rank_top_k={
            k: average is not None and average <= k for k in TOP_K_VALUES
        },
    )


def aggregate_metrics(metrics: list[CaseMetric]) -> dict[str, Any]:
    total = len(metrics)
    result: dict[str, Any] = {"evaluated_cases": total}
    for k in TOP_K_VALUES:
        hits = sum(metric.top_k[k] for metric in metrics)
        result[f"top_{k}_hits"] = hits
        result[f"top_{k}_accuracy"] = hits / total if total else 0.0
    result["mrr"] = (
        sum(metric.reciprocal_rank for metric in metrics) / total
        if total
        else 0.0
    )
    modes = {
        "optimistic": ("best_fault_rank", "optimistic_top_k"),
        "pessimistic": ("worst_fault_rank", "pessimistic_top_k"),
        "average_rank": ("average_fault_rank", "average_rank_top_k"),
    }
    tie_aware: dict[str, dict[str, float | int]] = {}
    for mode, (rank_field, top_k_field) in modes.items():
        mode_result: dict[str, float | int] = {}
        for k in TOP_K_VALUES:
            hits = sum(getattr(metric, top_k_field)[k] for metric in metrics)
            mode_result[f"top_{k}_hits"] = hits
            mode_result[f"top_{k}_accuracy"] = hits / total if total else 0.0
        ranks = [getattr(metric, rank_field) for metric in metrics]
        mode_result["mrr"] = (
            sum(1.0 / rank for rank in ranks if rank is not None) / total
            if total
            else 0.0
        )
        tie_aware[mode] = mode_result
    result["tie_aware"] = tie_aware
    return result
