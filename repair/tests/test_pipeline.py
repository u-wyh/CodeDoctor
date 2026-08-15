"""Single-attempt pipeline and resume tests."""

import tempfile
import unittest
from pathlib import Path

from benchmark.config import CODEFLAWS_SAMPLE_ROOT
from benchmark.models import load_manifest
from repair.artifacts import ArtifactStore
from repair.models import (
    EvidenceGroup,
    ModelParameters,
    PatchClassification,
    PatchEvaluation,
    TestResult,
)
from repair.pipeline import run_repair_attempt
from repair.provider import FakeRepairModel


def evaluation(validated: bool) -> PatchEvaluation:
    repair = (TestResult("r", True, "", "", 0, False),)
    validation = (TestResult("v", validated, "", "", 0, False),)
    return PatchEvaluation(
        True,
        "",
        "",
        0,
        repair,
        validation,
        True,
        validated,
        (
            PatchClassification.VALIDATED_PATCH
            if validated
            else PatchClassification.PLAUSIBLE_PATCH
        ),
        () if validated else ("validation_overfitting",),
    )


class PipelineTests(unittest.TestCase):
    def test_completed_attempt_is_resumed_exactly_once(self) -> None:
        case = next(load_manifest(CODEFLAWS_SAMPLE_ROOT / "sample_manifest.jsonl"))
        source = case.get_buggy_source()
        parameters = ModelParameters("fake", "fake://", "m", 0.0, 100, 1.0)
        model = FakeRepairModel(parameters, f"```c\n{source}\n```")
        baseline = evaluation(False)
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            first = run_repair_attempt(
                case,
                EvidenceGroup.SOURCE_ONLY,
                model,
                None,
                baseline,
                store,
                resume=True,
                evaluator=lambda _case, _source: evaluation(True),
                experimental=False,
            )
            second = run_repair_attempt(
                case,
                EvidenceGroup.SOURCE_ONLY,
                model,
                None,
                baseline,
                store,
                resume=True,
                evaluator=lambda _case, _source: evaluation(True),
                experimental=False,
            )
        self.assertEqual("validated_patch", first["classification"])
        self.assertEqual(first, second)
        self.assertEqual(1, model.calls)


if __name__ == "__main__":
    unittest.main()
