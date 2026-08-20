import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.config import REPAIR_EVALUATION
from benchmark.frozen_artifacts import FrozenArtifactError
from validation_phase9.corpus import build_formal_patch_corpus


class Phase9ArtifactGuardTests(unittest.TestCase):
    def test_missing_package_fails_before_frozen_output_is_modified(self):
        before = REPAIR_EVALUATION.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch("validation_phase9.corpus.REPAIR_ARTIFACT_ROOT", root / "repair"),
                patch("validation_phase9.corpus.PHASE8_ARTIFACT_ROOT", root / "phase8"),
                self.assertRaisesRegex(
                    FrozenArtifactError, "Required frozen artifact missing"
                ) as raised,
            ):
                build_formal_patch_corpus()
        self.assertIn("Missing artifact list", str(raised.exception))
        self.assertIn("Phase 7", str(raised.exception))
        self.assertIn("Phase 8", str(raised.exception))
        self.assertEqual(before, REPAIR_EVALUATION.read_bytes())


if __name__ == "__main__":
    unittest.main()
