"""Provider success and failure behavior without network calls."""

import unittest

from repair.models import EvidenceGroup, ModelParameters, PromptDocument
from repair.provider import (
    FakeRepairModel,
    MalformedModelResponse,
    ModelAPIError,
    ModelTimeout,
)


PARAMETERS = ModelParameters("fake", "fake://local", "fake-v1", 0.0, 100, 1.0)
PROMPT = PromptDocument("v1", EvidenceGroup.SOURCE_ONLY, "system", "user", "hash")


class ProviderTests(unittest.TestCase):
    def test_fake_success(self) -> None:
        model = FakeRepairModel(PARAMETERS, "source")
        self.assertEqual("source", model.generate(PROMPT).text)

    def test_fake_timeout(self) -> None:
        model = FakeRepairModel(PARAMETERS, "")
        model.error = ModelTimeout("timeout")
        with self.assertRaises(ModelTimeout):
            model.generate(PROMPT)

    def test_fake_api_error(self) -> None:
        model = FakeRepairModel(PARAMETERS, "")
        model.error = ModelAPIError("api error")
        with self.assertRaises(ModelAPIError):
            model.generate(PROMPT)

    def test_fake_malformed_response(self) -> None:
        model = FakeRepairModel(PARAMETERS, "")
        model.error = MalformedModelResponse("malformed")
        with self.assertRaises(MalformedModelResponse):
            model.generate(PROMPT)


if __name__ == "__main__":
    unittest.main()
