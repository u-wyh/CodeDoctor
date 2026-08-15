"""Small, dependency-free paired statistical procedures for FL evaluation."""

import math
import random
import statistics
from typing import Sequence


def paired_change_counts(
    baseline: Sequence[float], treatment: Sequence[float], *, tolerance: float = 1e-15
) -> dict[str, int]:
    if len(baseline) != len(treatment):
        raise ValueError("paired samples must have equal length")
    improved = unchanged = regressed = 0
    for before, after in zip(baseline, treatment):
        difference = after - before
        if difference > tolerance:
            improved += 1
        elif difference < -tolerance:
            regressed += 1
        else:
            unchanged += 1
    return {
        "improved": improved,
        "unchanged": unchanged,
        "regressed": regressed,
    }


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return (
        sorted_values[lower] * (1.0 - fraction)
        + sorted_values[upper] * fraction
    )


def paired_bootstrap_difference(
    baseline: Sequence[float],
    treatment: Sequence[float],
    *,
    samples: int = 10_000,
    seed: int = 20260816,
) -> dict[str, float | int | list[float]]:
    if len(baseline) != len(treatment):
        raise ValueError("paired samples must have equal length")
    if not baseline:
        raise ValueError("bootstrap requires at least one pair")
    if samples <= 0:
        raise ValueError("samples must be positive")

    differences = [after - before for before, after in zip(baseline, treatment)]
    randomizer = random.Random(seed)
    count = len(differences)
    bootstrap = []
    for _ in range(samples):
        bootstrap.append(
            sum(differences[randomizer.randrange(count)] for _ in range(count))
            / count
        )
    bootstrap.sort()
    return {
        "bootstrap_mean": statistics.fmean(bootstrap),
        "confidence_interval_95": [
            _percentile(bootstrap, 0.025),
            _percentile(bootstrap, 0.975),
        ],
        "observed_difference": statistics.fmean(differences),
        "samples": samples,
        "seed": seed,
    }


def exact_mcnemar(
    baseline: Sequence[bool], treatment: Sequence[bool]
) -> dict[str, float | int]:
    if len(baseline) != len(treatment):
        raise ValueError("paired outcomes must have equal length")
    both_success = baseline_only = treatment_only = both_fail = 0
    for before, after in zip(baseline, treatment):
        if before and after:
            both_success += 1
        elif before:
            baseline_only += 1
        elif after:
            treatment_only += 1
        else:
            both_fail += 1
    discordant = baseline_only + treatment_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, value)
            for value in range(min(baseline_only, treatment_only) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        "baseline_only": baseline_only,
        "both_fail": both_fail,
        "both_success": both_success,
        "discordant": discordant,
        "exact_two_sided_p_value": p_value,
        "treatment_only": treatment_only,
    }
