"""DeepSeek compatibility, usage, credential, and secret-boundary tests."""

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from benchmark.config import DEEPSEEK_EXPERIMENT_CONFIG
from repair.artifacts import ArtifactStore
from repair.deepseek import (
    DeepSeekProvider,
    attach_response_metadata,
    model_parameters,
    resolve_api_key,
    validate_configuration,
)
from repair.models import EvidenceGroup, PromptDocument
from repair.provider import ModelAPIError


PROMPT = PromptDocument(
    "repair-evidence-v2",
    EvidenceGroup.SOURCE_ONLY,
    "system",
    "user",
    "hash",
)


class FakeHTTPResponse:
    def __init__(self, value: dict[str, object]):
        self.value = value

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.value).encode()

    def close(self) -> None:
        return None


class DeepSeekTests(unittest.TestCase):
    def test_frozen_configuration(self) -> None:
        value = validate_configuration(DEEPSEEK_EXPERIMENT_CONFIG)
        self.assertEqual("deepseek-v4-pro", value["model"])
        self.assertEqual(8192, value["max_tokens"])
        self.assertEqual("enabled", value["thinking"]["type"])

    def test_key_priority_never_uses_openai_key(self) -> None:
        key, source = resolve_api_key(
            {
                "DEEPSEEK_API_KEY": "deepseek-secret",
                "CODEDOCTOR_API_KEY": "generic-secret",
                "OPENAI_API_KEY": "wrong-secret",
            }
        )
        self.assertEqual(("deepseek-secret", "DEEPSEEK_API_KEY"), (key, source))
        self.assertEqual(
            ("generic-secret", "CODEDOCTOR_API_KEY"),
            resolve_api_key(
                {
                    "CODEDOCTOR_API_KEY": "generic-secret",
                    "OPENAI_API_KEY": "wrong-secret",
                }
            ),
        )
        self.assertEqual(
            (None, None), resolve_api_key({"OPENAI_API_KEY": "wrong-secret"})
        )

    def test_request_and_response_boundaries(self) -> None:
        document = {
            "id": "response-1",
            "model": "deepseek-v4-pro",
            "created": 123,
            "system_fingerprint": "fp-test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "final source",
                        "reasoning_content": "private reasoning",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
                "prompt_cache_hit_tokens": 2,
                "prompt_cache_miss_tokens": 8,
                "completion_tokens_details": {"reasoning_tokens": 15},
            },
        }
        provider = DeepSeekProvider(
            model_parameters(5.0), "test-secret", "DEEPSEEK_API_KEY"
        )
        with patch(
            "repair.deepseek.urllib.request.urlopen",
            return_value=FakeHTTPResponse(document),
        ) as mocked:
            response = provider.generate(PROMPT)
        request = mocked.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual("final source", response.text)
        self.assertNotIn("private reasoning", response.text)
        self.assertEqual(False, payload["stream"])
        self.assertEqual({"type": "enabled"}, payload["thinking"])
        self.assertEqual("high", payload["reasoning_effort"])
        self.assertEqual(8192, payload["max_tokens"])
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        metadata = provider.consume_response_metadata()
        self.assertIsNotNone(metadata)
        serialized = json.dumps(metadata)
        self.assertNotIn("private reasoning", serialized)
        self.assertNotIn("test-secret", serialized)
        self.assertEqual(15, metadata["usage"]["completion_tokens_details"]["reasoning_tokens"])

    def test_artifact_metadata_contains_usage_but_no_secret_or_reasoning(self) -> None:
        metadata = {
            "credential_environment": "DEEPSEEK_API_KEY",
            "reasoning_content": {
                "present": True,
                "characters": 10,
                "sha256": "abc",
            },
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        record = {
            "cache_key": "key",
            "case_id": "case",
            "group": "A",
            "model_response": {"id": "response"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary))
            result = attach_response_metadata(store, record, metadata)
        serialized = json.dumps(result)
        self.assertIn("prompt_tokens", serialized)
        self.assertNotIn("reasoning text", serialized)
        self.assertNotIn("secret", serialized.lower())

    def test_http_error_redacts_key_before_pipeline_storage(self) -> None:
        provider = DeepSeekProvider(
            model_parameters(5.0), "actual-test-key", "DEEPSEEK_API_KEY"
        )
        error = urllib.error.HTTPError(
            "https://api.deepseek.com/chat/completions",
            401,
            "Unauthorized",
            {},
            FakeHTTPResponse({"error": "actual-test-key rejected"}),
        )
        with patch(
            "repair.deepseek.urllib.request.urlopen", side_effect=error
        ), self.assertRaises(ModelAPIError) as raised:
            provider.generate(PROMPT)
        self.assertNotIn("actual-test-key", str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
