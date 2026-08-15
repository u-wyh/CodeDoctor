"""Content-addressed cache behavior."""

import tempfile
import unittest
from pathlib import Path

from repair.artifacts import ArtifactStore, cache_key
from repair.models import EvidenceGroup, ModelParameters, PromptDocument


class ArtifactTests(unittest.TestCase):
    def test_same_configuration_resumes_but_parameters_change_key(self) -> None:
        prompt = PromptDocument("v1", EvidenceGroup.SOURCE_ONLY, "s", "u", "ph")
        first = ModelParameters("fake", "fake://", "m", 0.0, 10, 2.0)
        second = ModelParameters("fake", "fake://", "m", 0.1, 10, 2.0)
        key = cache_key("case", EvidenceGroup.SOURCE_ONLY, prompt, first)
        self.assertEqual(key, cache_key("case", EvidenceGroup.SOURCE_ONLY, prompt, first))
        self.assertNotEqual(key, cache_key("case", EvidenceGroup.SOURCE_ONLY, prompt, second))
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            store.write("case", EvidenceGroup.SOURCE_ONLY, key, {"completed": True})
            self.assertEqual(
                {"completed": True},
                store.load("case", EvidenceGroup.SOURCE_ONLY, key),
            )


if __name__ == "__main__":
    unittest.main()
