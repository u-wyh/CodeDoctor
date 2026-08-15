"""Suspiciousness formulas used by spectrum-based fault localization."""

import math
import sys
from collections.abc import Callable

from .models import SpectrumBranch, SpectrumLine


SpectrumRecord = SpectrumLine | SpectrumBranch
SuspiciousnessFormula = Callable[[SpectrumRecord], float]


def ochiai(spectrum: SpectrumRecord) -> float:
    denominator = math.sqrt(
        (spectrum.ef + spectrum.nf) * (spectrum.ef + spectrum.ep)
    )
    return spectrum.ef / denominator if denominator else 0.0


def tarantula(spectrum: SpectrumRecord) -> float:
    total_failed = spectrum.ef + spectrum.nf
    total_passed = spectrum.ep + spectrum.np
    failed_rate = spectrum.ef / total_failed if total_failed else 0.0
    passed_rate = spectrum.ep / total_passed if total_passed else 0.0
    denominator = failed_rate + passed_rate
    return failed_rate / denominator if denominator else 0.0


def dstar2(spectrum: SpectrumRecord) -> float:
    denominator = spectrum.ep + spectrum.nf
    if denominator == 0:
        return sys.float_info.max if spectrum.ef > 0 else 0.0
    return spectrum.ef**2 / denominator


ALGORITHMS: dict[str, SuspiciousnessFormula] = {
    "ochiai": ochiai,
    "tarantula": tarantula,
    "dstar2": dstar2,
}
