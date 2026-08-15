"""Tests for paired FL statistics."""

import unittest

from fault_localization.statistics import (
    exact_mcnemar,
    paired_bootstrap_difference,
    paired_change_counts,
)


class PairedStatisticsTests(unittest.TestCase):
    def test_paired_change_counts(self) -> None:
        self.assertEqual(
            {"improved": 1, "unchanged": 1, "regressed": 1},
            paired_change_counts([0.1, 0.2, 0.3], [0.2, 0.2, 0.1]),
        )

    def test_bootstrap_is_reproducible_and_paired(self) -> None:
        first = paired_bootstrap_difference(
            [0.0, 0.0, 0.0], [0.25, 0.25, 0.25], samples=100, seed=7
        )
        second = paired_bootstrap_difference(
            [0.0, 0.0, 0.0], [0.25, 0.25, 0.25], samples=100, seed=7
        )
        self.assertEqual(first, second)
        self.assertEqual(0.25, first["observed_difference"])
        self.assertEqual([0.25, 0.25], first["confidence_interval_95"])

    def test_exact_mcnemar_uses_discordant_pairs(self) -> None:
        result = exact_mcnemar(
            [False] * 5,
            [True] * 5,
        )
        self.assertEqual(0, result["baseline_only"])
        self.assertEqual(5, result["treatment_only"])
        self.assertEqual(0.0625, result["exact_two_sided_p_value"])


if __name__ == "__main__":
    unittest.main()
