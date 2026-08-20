"""Paired Stage 2 statistics and report-discipline tests."""

import unittest

from repair_phase8.stage2_reporting import paired_statistics, render_final_report


class Stage2ReportingTests(unittest.TestCase):
    def test_paired_statistics_match_frozen_six_case_outcomes(self) -> None:
        value = paired_statistics(
            [(False, True), (True, True), (True, False), (True, True), (False, False), (True, True)]
        )
        self.assertEqual(3, value["both_success"])
        self.assertEqual(1, value["retry_fail_feedback_success"])
        self.assertEqual(1, value["retry_success_feedback_fail"])
        self.assertEqual(1, value["both_fail"])
        self.assertEqual(0.0, value["feedback_minus_retry"])
        self.assertEqual(-0.5, value["bootstrap_95_ci"]["lower"])
        self.assertEqual(0.5, value["bootstrap_95_ci"]["upper"])
        self.assertEqual(1.0, value["mcnemar_exact"]["p_value_two_sided"])

    def test_report_states_required_limitations(self) -> None:
        paired = paired_statistics([(False, True), (True, False)])
        entry = {
            "arm": "retry_control",
            "case_id": "case",
            "classification": "validated_patch",
            "validated": True,
        }
        feedback = dict(entry, arm="feedback")
        value = {
            "artifact_set_hash": "artifacts",
            "calls": {"attempted": 2, "received": 2, "provider_failures": 0},
            "end_to_end": {
                "S0_initial_only": {"validated": 85, "rate": 0.85},
                "SR_initial_plus_retry": {"validated": 86, "rate": 0.86},
                "SF_initial_plus_feedback": {"validated": 86, "rate": 0.86},
            },
            "entries": [entry, feedback],
            "failure_modes": {"feedback": {}, "retry_control": {}},
            "leakage_audit": {"status": "passed"},
            "overall_manifest_hash": "manifest",
            "paired": paired,
            "usage_and_cost": {
                "feedback": {"cost_usd": 0.05, "tokens": {}},
                "retry_control": {"cost_usd": 0.05, "tokens": {}},
                "total": {"cost_usd": 0.1, "tokens": {
                    "prompt_tokens": 1, "prompt_cache_hit_tokens": 1,
                    "prompt_cache_miss_tokens": 0, "reasoning_tokens": 1,
                    "final_answer_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
                }},
            },
        }
        report = render_final_report(value)
        self.assertIn("Validated Patch != Formally Correct Patch", report)
        self.assertIn("paired case-level", report)
        self.assertIn("M=6", report)


if __name__ == "__main__":
    unittest.main()
