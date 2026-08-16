"""DeepSeek pre-experiment token projection and cost tests."""

import unittest

from repair.pre_experiment import (
    _actual_smoke_cost,
    _bulk_projection,
    _cache_miss_cost,
    _complete_smoke,
    approximate_tokens,
)


class PreExperimentTests(unittest.TestCase):
    def test_provider_independent_projection_without_real_usage(self) -> None:
        groups = {
            "A": {"approximate_total_input_tokens": 18_800},
            "B": {"approximate_total_input_tokens": 29_700},
            "C": {"approximate_total_input_tokens": 34_400},
        }
        usage = {group: {"calls": 0, "usage": None} for group in "ABC"}
        projection = _bulk_projection(groups, 24_600, usage)
        self.assertIn("no real DeepSeek smoke", projection["basis"])
        self.assertIsNone(projection["reasoning_total"])
        self.assertEqual("buggy-source length proxy", projection["output_basis"])
        self.assertEqual(82_900, sum(projection["input_by_group"].values()))
        self.assertEqual(
            0.057464,
            _cache_miss_cost(
                projection, {"input_cache_miss": 0.435, "output": 0.87}
            ),
        )

    def test_real_usage_projection_includes_reasoning(self) -> None:
        groups = {
            group: {"approximate_total_input_tokens": 100} for group in "ABC"
        }
        usage = {
            group: {
                "calls": 1,
                "usage": {
                    "prompt_tokens": index,
                    "completion_tokens": index * 2,
                    "reasoning_tokens": index,
                },
            }
            for index, group in enumerate("ABC", start=1)
        }
        projection = _bulk_projection(
            groups,
            1,
            usage,
            {"A": 1, "B": 2, "C": 3},
            smoke_truncated=True,
        )
        self.assertEqual({"A": 100, "B": 100, "C": 100}, projection["input_by_group"])
        self.assertEqual(600, projection["output_total"])
        self.assertEqual(300, projection["reasoning_total"])
        self.assertIn("conservative cap", projection["output_basis"])

    def test_actual_smoke_cost_uses_cache_split(self) -> None:
        usage = {
            group: {
                "calls": 1,
                "usage": {
                    "completion_tokens": 100,
                    "prompt_cache_hit_tokens": 20,
                    "prompt_cache_miss_tokens": 30,
                },
            }
            for group in "ABC"
        }
        prices = {
            "input_cache_hit": 1.0,
            "input_cache_miss": 2.0,
            "output": 3.0,
        }
        self.assertEqual(0.00114, _actual_smoke_cost(usage, prices))

    def test_token_heuristic_is_explicit(self) -> None:
        self.assertEqual(2, approximate_tokens("12345"))

    def test_smoke_requires_usage_final_content_and_no_truncation(self) -> None:
        usage = {
            group: {
                "calls": 1,
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                },
            }
            for group in "ABC"
        }
        records = [
            {
                "group": group,
                "classification": "repair_test_failed",
                "model_response": {"finish_reason": "stop"},
            }
            for group in "ABC"
        ]
        self.assertTrue(_complete_smoke(records, usage))
        records[2]["model_response"]["finish_reason"] = "length"
        self.assertFalse(_complete_smoke(records, usage))


if __name__ == "__main__":
    unittest.main()
