"""Tests for deterministic ranking and Top-K evaluation."""

import unittest

from fault_localization.evaluation import aggregate_metrics, evaluate_case
from fault_localization.models import RankedLine, SpectrumLine
from fault_localization.ranking import rank_spectrum, rank_with_branch_tiebreak


class RankingTests(unittest.TestCase):
    def test_ties_use_line_number_and_record_tie_range(self) -> None:
        spectrum = (
            SpectrumLine(10, 1, 0, 0, 1),
            SpectrumLine(5, 1, 0, 0, 1),
            SpectrumLine(20, 0, 0, 1, 1),
        )
        ranking = rank_spectrum(
            spectrum, lambda item: float(item.ef), "\n" * 20
        )
        self.assertEqual([5, 10, 20], [item.line for item in ranking])
        self.assertEqual((1, 2), (ranking[0].tie_start_rank, ranking[0].tie_end_rank))
        self.assertEqual((1, 2), (ranking[1].tie_start_rank, ranking[1].tie_end_rank))
        self.assertEqual(0.0, ranking[2].score)

    def test_metrics_use_deterministic_position_rank(self) -> None:
        ranking = tuple(
            RankedLine(
                rank=index,
                line=line,
                score=1.0 / index,
                ef=1,
                ep=0,
                nf=0,
                np=1,
                source_snippet="",
                tie_start_rank=index,
                tie_end_rank=index,
            )
            for index, line in enumerate((10, 20, 30, 40), start=1)
        )
        metric = evaluate_case(ranking, (30,))
        self.assertEqual(3, metric.first_fault_rank)
        self.assertFalse(metric.top_k[1])
        self.assertTrue(metric.top_k[3])
        aggregate = aggregate_metrics([metric])
        self.assertEqual(1.0, aggregate["top_3_accuracy"])
        self.assertAlmostEqual(1 / 3, aggregate["mrr"])

    def test_tie_aware_metric_uses_tie_interval(self) -> None:
        ranking = rank_spectrum(
            (
                SpectrumLine(10, 1, 0, 0, 1),
                SpectrumLine(20, 1, 0, 0, 1),
                SpectrumLine(30, 1, 0, 0, 1),
                SpectrumLine(40, 1, 0, 0, 1),
            ),
            lambda item: 0.91,
            "\n" * 40,
        )
        metric = evaluate_case(ranking, (30,))
        self.assertEqual(1, metric.best_fault_rank)
        self.assertEqual(4, metric.worst_fault_rank)
        self.assertEqual(2.5, metric.average_fault_rank)
        self.assertEqual(4, metric.fault_tie_size)
        aggregate = aggregate_metrics([metric])
        self.assertEqual(1.0, aggregate["tie_aware"]["optimistic"]["mrr"])
        self.assertEqual(0.25, aggregate["tie_aware"]["pessimistic"]["mrr"])
        self.assertEqual(0.4, aggregate["tie_aware"]["average_rank"]["mrr"])

    def test_branch_score_breaks_only_exact_line_score_ties(self) -> None:
        ranking = rank_with_branch_tiebreak(
            (
                SpectrumLine(10, 2, 0, 0, 1),
                SpectrumLine(20, 1, 0, 1, 1),
                SpectrumLine(30, 1, 0, 1, 1),
            ),
            lambda item: float(item.ef),
            {10: 0.0, 20: 0.2, 30: 0.8},
            "\n" * 30,
        )
        self.assertEqual([10, 30, 20], [item.line for item in ranking])
        self.assertEqual((2, 2), (
            ranking[1].tie_start_rank, ranking[1].tie_end_rank
        ))

    def test_missing_fault_line_scores_zero(self) -> None:
        metric = evaluate_case((), (99,))
        self.assertIsNone(metric.first_fault_rank)
        self.assertEqual(0.0, metric.reciprocal_rank)
        self.assertTrue(all(not value for value in metric.top_k.values()))


if __name__ == "__main__":
    unittest.main()
