import hashlib
import tempfile
import unittest
from pathlib import Path

from benchmark.frozen_artifacts import (
    FrozenArtifactError,
    require_artifact_groups,
    require_frozen_file,
)


class FrozenArtifactGuardTests(unittest.TestCase):
    def test_missing_mismatch_and_restore_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact.json"
            sentinel = root / "tracked-result.json"
            sentinel.write_text("frozen\n", encoding="utf-8")
            before = sentinel.read_bytes()
            expected = hashlib.sha256(b"correct\n").hexdigest()

            with self.assertRaisesRegex(
                FrozenArtifactError, "Required frozen artifact missing"
            ):
                require_frozen_file(artifact, expected, "test artifact")
            self.assertEqual(before, sentinel.read_bytes())

            artifact.write_text("wrong\n", encoding="utf-8")
            with self.assertRaisesRegex(FrozenArtifactError, "hash mismatch"):
                require_frozen_file(artifact, expected, "test artifact")
            self.assertEqual(before, sentinel.read_bytes())

            artifact.write_text("correct\n", encoding="utf-8")
            self.assertEqual(
                artifact, require_frozen_file(artifact, expected, "test artifact")
            )
            self.assertEqual(before, sentinel.read_bytes())

    def test_missing_group_error_lists_every_required_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FrozenArtifactError) as raised:
                require_artifact_groups(
                    (
                        ("Phase 7", root / "phase7", "*/*.json", 150),
                        ("Phase 9", root / "phase9", "*.json", 245),
                    )
                )
        message = str(raised.exception)
        self.assertIn("Missing artifact list", message)
        self.assertIn("Phase 7", message)
        self.assertIn("Phase 9", message)


if __name__ == "__main__":
    unittest.main()
