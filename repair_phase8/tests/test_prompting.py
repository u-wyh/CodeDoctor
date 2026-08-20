import unittest

from repair.models import RepairContext, RepairTestEvidence, SuspiciousLocation, TaskExample
from repair_phase8.models import Phase8Arm
from repair_phase8.prompting import render_initial_prompt, render_second_prompt
from repair_phase8.evidence_rendering import RENDER_PROTOCOL_VERSION


SOURCE = "int main(){return 1;}"


class PromptBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        context = RepairContext(
            "case",
            "cpp",
            SOURCE,
            (
                TaskExample("base", "1\n", "2\n"),
                TaskExample("feedback", "3\n", "4\n"),
            ),
            "available",
            (SuspiciousLocation(1, 1, SOURCE, 1.0, None, 1, 1),),
            (RepairTestEvidence("base", "FAIL", "0\n", "", 0, False),),
        )
        self.initial = render_initial_prompt(context, {"base"})
        self.feedback = {
            "failed_tests": [
                {
                    "test_id": "feedback",
                    "input": "3\n",
                    "expected_output": "4\n",
                    "actual_stdout": "ACTUAL_CANARY\n",
                    "stderr": "",
                    "exit_code": 0,
                    "timed_out": False,
                    "verdict": "FAIL",
                }
            ]
        }

    def test_initial_and_retry_have_no_evaluation_or_feedback_canaries(self) -> None:
        evaluation_canaries = ("REFERENCE_SECRET_TOKEN", "VALIDATION_SECRET_TOKEN")
        retry = render_second_prompt(
            self.initial, SOURCE, Phase8Arm.RETRY_CONTROL
        )
        for prompt in (self.initial, retry):
            for canary in evaluation_canaries:
                self.assertNotIn(canary, prompt.user)
        self.assertNotIn("ACTUAL_CANARY", retry.user)
        self.assertNotIn("Failed repair-time execution feedback", retry.user)

    def test_feedback_only_adds_failed_repair_time_observation(self) -> None:
        retry = render_second_prompt(self.initial, SOURCE, Phase8Arm.RETRY_CONTROL)
        feedback = render_second_prompt(
            self.initial, SOURCE, Phase8Arm.FEEDBACK, self.feedback
        )
        self.assertIn(retry.user, feedback.user)
        self.assertIn("ACTUAL_CANARY", feedback.user)
        self.assertNotIn("REFERENCE_SECRET_TOKEN", feedback.user)
        self.assertNotIn("VALIDATION_SECRET_TOKEN", feedback.user)

    def test_empty_base_oracle_is_explicitly_supported(self) -> None:
        context = RepairContext(
            "case",
            "cpp",
            SOURCE,
            (TaskExample("feedback", "3\n", "4\n"),),
            "No reliable suspicious location is available from FL-v1.",
            (),
            (RepairTestEvidence("feedback", "FAIL", "0\n", "", 0, False),),
        )
        prompt = render_initial_prompt(context, set())
        self.assertIn("No original Base Repair Tests", prompt.user)
        self.assertIn("### feedback", prompt.user)

    def test_stage2_feedback_reuses_bounded_renderer(self) -> None:
        feedback = {
            "failed_tests": [
                {
                    "test_id": "feedback",
                    "input": "3\n",
                    "expected_output": "4\n",
                    "actual_stdout": "x" * (10 * 1024 * 1024),
                    "stderr": "e" * (10 * 1024 * 1024),
                    "exit_code": 1,
                    "timed_out": False,
                    "verdict": "FAIL",
                }
            ]
        }
        prompt = render_second_prompt(
            self.initial, SOURCE, Phase8Arm.FEEDBACK, feedback
        )
        self.assertEqual(RENDER_PROTOCOL_VERSION, prompt.render_protocol_version)
        self.assertLess(len(prompt.user.encode()), 30000)
        self.assertIn("stdout_omitted_bytes", prompt.user)
        self.assertIn("stderr_omitted_bytes", prompt.user)
        self.assertNotIn("Input:\n```text", prompt.user.split("Failed repair-time", 1)[1])


if __name__ == "__main__":
    unittest.main()
