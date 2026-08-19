"""Repair aggregation, paired statistics, and artifact leakage tests."""

import unittest

from repair.reporting import (
    _artifact_integrity,
    _group_metrics,
    _is_formal_artifact,
    _paired_comparison,
    _usage_metrics,
    validate_artifact_boundaries,
)


def record(case_id: str, group: str, validated: bool) -> dict[str, object]:
    return {
        "attempt": 1,
        "cache_key": f"{case_id}-{group}",
        "case_id": case_id,
        "classification": "validated_patch" if validated else "repair_test_failed",
        "evaluation": {
            "compile_success": True,
            "plausible": validated,
            "validated": validated,
        },
        "group": group,
        "experiment_role": "formal_evidence_ablation",
        "model_parameters": {"model": "fake"},
        "prompt": {
            "hash": f"hash-{case_id}-{group}",
            "system": "system",
            "user": (
                "source\n## Common repair-time oracle\nExpected output:\nvalue"
                + ("\n\n## CodeDoctor FL-v1 suspicious locations" if group in "BC" else "")
                + ("\n\n## Repair-test execution evidence" if group == "C" else "")
            ),
        },
    }


class ReportingTests(unittest.TestCase):
    def test_engineering_smoke_is_excluded_from_formal_metrics(self) -> None:
        smoke = {
            "experimental": True,
            "experiment_role": "pre_experiment_smoke",
            "model_parameters": {"provider": "deepseek"},
        }
        formal = dict(smoke, experiment_role="formal_evidence_ablation")
        legacy_deepseek = {
            "experimental": True,
            "model_parameters": {"provider": "deepseek"},
        }
        self.assertFalse(_is_formal_artifact(smoke))
        self.assertTrue(_is_formal_artifact(formal))
        self.assertFalse(_is_formal_artifact(legacy_deepseek))

    def test_group_metrics_and_paired_validated_outcome(self) -> None:
        records = [record("x", "A", False), record("y", "A", True)]
        metric = _group_metrics(records)
        self.assertEqual(2, metric["total"])
        self.assertEqual(0.5, metric["validated_rate"])
        paired = _paired_comparison(
            {
                "x": {"A": record("x", "A", False), "B": record("x", "B", True)},
                "y": {"A": record("y", "A", True), "B": record("y", "B", False)},
            },
            "A",
            "B",
        )
        self.assertEqual("available", paired["status"])
        self.assertEqual(1, paired["mcnemar"]["baseline_only"])
        self.assertEqual(1, paired["mcnemar"]["treatment_only"])
        self.assertEqual(0.0, paired["bootstrap"]["observed_difference"])

    def test_artifact_group_boundaries_and_canaries(self) -> None:
        values = [record("x", group, False) for group in "ABC"]
        self.assertEqual("passed", validate_artifact_boundaries(values)["status"])
        values[0]["prompt"]["user"] += " REFERENCE_SECRET_TOKEN"
        with self.assertRaises(ValueError):
            validate_artifact_boundaries(values)

    def test_usage_and_artifact_integrity(self) -> None:
        values = [record("x", group, False) for group in "ABC"]
        values[0]["provider_response_metadata"] = {
            "request_configuration": {"max_tokens": 1},
            "response_model": "deepseek-v4-flash",
            "system_fingerprint": "fingerprint",
            "usage": {
                "completion_tokens": 30,
                "completion_tokens_details": {"reasoning_tokens": 20},
                "final_answer_tokens": 10,
                "prompt_cache_hit_tokens": 5,
                "prompt_cache_miss_tokens": 15,
                "prompt_tokens": 20,
                "total_tokens": 50,
            }
        }
        usage = _usage_metrics(
            values,
            {"input_cache_hit": 1.0, "input_cache_miss": 2.0, "output": 3.0},
        )
        self.assertEqual(1, usage["calls_with_usage"])
        self.assertEqual(20, usage["reasoning_tokens"])
        self.assertEqual(0.000125, usage["estimated_cost_usd"])
        audit = {
            "prompt_set_hash": "set-hash",
            "runtime_evidence_manifest_hash": "runtime-hash",
            "prompt_records": [
                {
                    "case_id": item["case_id"],
                    "group": item["group"],
                    "prompt_hash": item["prompt"]["hash"],
                }
                for item in values
            ],
        }
        integrity = _artifact_integrity(values, audit)
        self.assertTrue(integrity["prompt_hashes_match_frozen_audit"])
        self.assertTrue(integrity["attempt_one_only"])
        self.assertEqual(3, integrity["unique_cache_keys"])


if __name__ == "__main__":
    unittest.main()
