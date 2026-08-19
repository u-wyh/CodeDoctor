import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repair.models import ModelParameters
from repair.provider import FakeRepairModel, ModelAPIError
from repair_phase8.artifacts import Phase8ArtifactStore
from repair_phase8.models import Phase8Arm
from repair_phase8.pipeline import run_initial_attempt, run_second_attempt
from repair_phase8.prompting import render_initial_prompt
from repair_phase8.tests.test_evaluation import result
from repair_phase8.tests.test_partition import make_case
from repair_phase8.partition import derive_partition, partitioned_case
from repair.models import RepairContext, RepairTestEvidence, TaskExample


PARAMETERS = ModelParameters("fake", "fake://", "fake", None, 100, 1.0)


def setup_case():
    original = make_case(validation_count=2)
    case = partitioned_case(original, derive_partition(original, 20260820))
    feedback_id = case.metadata["phase8"]["feedback_test_ids"][0]
    context = RepairContext(
        case.case_id,
        "cpp",
        "int main(){return 1;}",
        (TaskExample("base", "", "0\n"), TaskExample(feedback_id, "", "0\n")),
        "No reliable suspicious location is available from FL-v1.",
        (),
        (RepairTestEvidence("base", "FAIL", "", "", 1, False),),
    )
    return case, feedback_id, render_initial_prompt(context, {"base"})


class PipelineTests(unittest.TestCase):
    def test_fake_end_to_end_scenarios_and_shared_first_patch(self) -> None:
        scenarios = {
            "compile": result(compile_success=False),
            "test": result(base=False),
            "success": result(),
            "hidden_only": result(hidden=False),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, content in {
                "base.in": "",
                "base.out": "0\n",
                "v0.in": "",
                "v0.out": "0\n",
                "v1.in": "",
                "v1.out": "0\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            for name, evaluation in scenarios.items():
                case, feedback_id, prompt = setup_case()
                case = type(case)(**{**case.__dict__, "case_id": name})
                model = FakeRepairModel(PARAMETERS, "```cpp\nint main(){return 0;}\n```")
                store = Phase8ArtifactStore(Path(temporary))
                with patch("repair_phase8.context.PROJECT_ROOT", root):
                    initial = run_initial_attempt(
                        case,
                        prompt,
                        model,
                        lambda _c, _s, e=evaluation, f=feedback_id: result(
                            base=e.repair_tests[0].passed if e.repair_tests else True,
                            feedback=e.repair_tests[1].passed if len(e.repair_tests) > 1 else True,
                            hidden=e.validation_tests[0].passed if e.validation_tests else True,
                            compile_success=e.compile_success,
                            feedback_id=f,
                        ),
                        store,
                        "partition",
                    )
                self.assertEqual(name in {"compile", "test"}, initial["second_round_eligible"])
                if initial["second_round_eligible"]:
                    retry = run_second_attempt(
                        case, prompt, initial, Phase8Arm.RETRY_CONTROL, model,
                        lambda _c, _s: result(feedback_id=feedback_id), store, "partition"
                    )
                    feedback = run_second_attempt(
                        case, prompt, initial, Phase8Arm.FEEDBACK, model,
                        lambda _c, _s: result(feedback_id=feedback_id), store, "partition"
                    )
                    self.assertEqual(retry["first_patch_hash"], feedback["first_patch_hash"])
                    self.assertNotIn("Failed repair-time execution feedback", retry["prompt"]["user"])
                    self.assertIn("Failed repair-time execution feedback", feedback["prompt"]["user"])

    def test_invalid_output_and_provider_failure_are_not_eligible(self) -> None:
        case, feedback_id, prompt = setup_case()
        with tempfile.TemporaryDirectory() as temporary:
            store = Phase8ArtifactStore(Path(temporary))
            invalid = FakeRepairModel(PARAMETERS, "")
            record = run_initial_attempt(
                case, prompt, invalid,
                lambda _c, _s: result(feedback_id=feedback_id), store, "p"
            )
            self.assertEqual("invalid_model_output", record["classification"])
            self.assertFalse(record["second_round_eligible"])
            failed = FakeRepairModel(PARAMETERS, "unused")
            failed.error = ModelAPIError("offline fake failure")
            record = run_initial_attempt(
                case, prompt, failed,
                lambda _c, _s: result(feedback_id=feedback_id), store, "q"
            )
            self.assertEqual("provider_failure", record["classification"])
            self.assertFalse(record["second_round_eligible"])


if __name__ == "__main__":
    unittest.main()
