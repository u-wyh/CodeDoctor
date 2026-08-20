"""Phase 8 Stage 1 aggregation and Stage 2 prompt audit tests."""

import unittest

from repair_phase8.reporting import _stats, render_stage1_report


class ReportingTests(unittest.TestCase):
    def test_stats_uses_nearest_rank_p95(self) -> None:
        self.assertEqual(5, _stats([1, 2, 3, 4, 5])["p95"])

    def test_report_explicitly_keeps_stage2_unstarted(self) -> None:
        summary = {
            "attempted_calls": 100,
            "compile_success": 91,
            "eligible_failure_distribution": {"feedback_test_failure": 1},
            "estimated_stage2_calls": 2,
            "estimated_stage2_cost_usd": 0.01,
            "finish_reason_distribution": {"stop": 100},
            "hidden_validation_only_failure": 0,
            "invalid_model_output": 9,
            "length_truncation": 9,
            "provider_failures": 0,
            "received_responses": 100,
            "repair_time_success": 90,
            "response_model_distribution": {"deepseek-v4-flash": 100},
            "second_round_eligible_count": 1,
            "stage1_artifact_set_hash": "stage1",
            "stage1_cost_usd": 0.02,
            "system_fingerprint_distribution": {"fingerprint": 100},
            "token_usage": {key: 1 for key in (
                "prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                "reasoning_tokens", "final_answer_tokens", "completion_tokens", "total_tokens"
            )},
            "valid_outputs": 91,
            "validated_patches": 90,
        }
        stats = {key: 1 for key in ("min", "median", "p95", "max")}
        audit = {
            "cohort_manifest_hash": "cohort",
            "eligible_count": 1,
            "leakage_audit": {"status": "passed"},
            "operational_size_gate": {"status": "passed"},
            "order_balance": {"retry_control->feedback": 1},
            "overall_manifest_hash": "audit",
            "payload_byte_statistics": {"retry_control": stats, "feedback": stats},
            "prompt_count": 2,
            "reproducibility": {"status": "passed"},
        }
        pricing = {
            "verified_at": "now",
            "prices": {"input_cache_hit": 1, "input_cache_miss": 1, "output": 1},
        }
        report = render_stage1_report(summary, audit, pricing)
        self.assertIn("no Stage 2 real LLM call has been made", report)
        self.assertIn("2M = 2", report)


if __name__ == "__main__":
    unittest.main()
