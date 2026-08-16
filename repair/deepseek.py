"""DeepSeek-specific compatibility over the frozen OpenAI-style repair boundary."""

import copy
import hashlib
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .models import EvidenceGroup, ModelParameters, ModelResponse, PromptDocument
from .provider import (
    MalformedModelResponse,
    ModelAPIError,
    ModelTimeout,
    OpenAICompatibleProvider,
)


PROVIDER = "deepseek"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"
THINKING_TYPE = "enabled"
REASONING_EFFORT = "high"
MAX_TOKENS = 8192
STREAM = False
TRANSPORT_RETRIES = 0
OFFICIAL_DOCUMENTED_MODEL_VERSION = "DeepSeek-V4-Pro-0813"


def resolve_api_key(environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    for name in ("DEEPSEEK_API_KEY", "CODEDOCTOR_API_KEY"):
        value = environ.get(name)
        if value:
            return value, name
    return None, None


def validate_configuration(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "api_format": "OpenAI-compatible Chat Completions",
        "base_url": BASE_URL,
        "credential_environment_priority": [
            "DEEPSEEK_API_KEY",
            "CODEDOCTOR_API_KEY",
        ],
        "maximum_repair_attempts": 1,
        "max_tokens": MAX_TOKENS,
        "model": MODEL,
        "official_documented_model_version": OFFICIAL_DOCUMENTED_MODEL_VERSION,
        "provider": PROVIDER,
        "provider_name": "DeepSeek Official API",
        "reasoning_effort": REASONING_EFFORT,
        "stream": STREAM,
        "temperature": "not_sent_ineffective_in_thinking_mode",
        "thinking": {"type": THINKING_TYPE},
        "transport_retries": TRANSPORT_RETRIES,
    }
    if value != expected:
        raise ValueError("DeepSeek experiment configuration differs from the freeze")
    return value


def model_parameters(timeout_seconds: float) -> ModelParameters:
    return ModelParameters(
        provider=PROVIDER,
        base_url=BASE_URL,
        model=MODEL,
        temperature=None,
        max_tokens=MAX_TOKENS,
        timeout_seconds=timeout_seconds,
        seed=None,
    )


def _usage_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = item
    details = value.get("completion_tokens_details")
    if isinstance(details, dict):
        reasoning_tokens = details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int) and not isinstance(reasoning_tokens, bool):
            result["completion_tokens_details"] = {
                "reasoning_tokens": reasoning_tokens
            }
    return result


class DeepSeekProvider(OpenAICompatibleProvider):
    """Single-turn DeepSeek adapter; extraction receives final content only."""

    def __init__(
        self,
        parameters: ModelParameters,
        api_key: str,
        credential_environment: str,
    ):
        super().__init__(parameters, api_key)
        if parameters != model_parameters(parameters.timeout_seconds):
            raise ValueError("DeepSeek model parameters differ from the freeze")
        if credential_environment not in {"DEEPSEEK_API_KEY", "CODEDOCTOR_API_KEY"}:
            raise ValueError("unsupported DeepSeek credential environment")
        self.credential_environment = credential_environment
        self.last_response_metadata: dict[str, Any] | None = None
        self.requests_attempted = 0
        self.responses_received = 0

    def request_payload(self, prompt: PromptDocument) -> dict[str, object]:
        return {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "thinking": {"type": THINKING_TYPE},
            "reasoning_effort": REASONING_EFFORT,
            "max_tokens": MAX_TOKENS,
            "stream": STREAM,
        }

    def generate(self, prompt: PromptDocument) -> ModelResponse:
        self.last_response_metadata = None
        self.requests_attempted += 1
        request = urllib.request.Request(
            BASE_URL + "/chat/completions",
            data=json.dumps(self.request_payload(prompt)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.parameters.timeout_seconds
            ) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise ModelTimeout("DeepSeek request timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            detail = detail.replace(self._api_key, "[REDACTED]")
            raise ModelAPIError(
                f"DeepSeek API returned HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ModelAPIError(f"DeepSeek API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MalformedModelResponse("DeepSeek API returned invalid JSON") from exc

        try:
            choice = document["choices"][0]
            message = choice["message"]
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("content is not text")
            reasoning = message.get("reasoning_content")
            if reasoning is not None and not isinstance(reasoning, str):
                raise TypeError("reasoning_content is not text")
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedModelResponse(
                "DeepSeek response does not contain final message.content"
            ) from exc

        self.responses_received += 1
        reasoning_summary = {
            "present": bool(reasoning),
        }
        if reasoning:
            reasoning_summary.update(
                {
                    "characters": len(reasoning),
                    "sha256": hashlib.sha256(reasoning.encode()).hexdigest(),
                }
            )
        self.last_response_metadata = {
            "created": document.get("created"),
            "credential_environment": self.credential_environment,
            "official_documented_model_version": OFFICIAL_DOCUMENTED_MODEL_VERSION,
            "requested_model": MODEL,
            "response_model": document.get("model"),
            "system_fingerprint": document.get("system_fingerprint"),
            "reasoning_content": reasoning_summary,
            "usage": _usage_summary(document.get("usage")),
        }
        return ModelResponse(
            text=content,
            response_id=document.get("id"),
            finish_reason=choice.get("finish_reason"),
        )

    def consume_response_metadata(self) -> dict[str, Any] | None:
        value = self.last_response_metadata
        self.last_response_metadata = None
        return value


def attach_response_metadata(
    store: ArtifactStore,
    record: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if metadata is None:
        return record
    response = record.get("model_response")
    if not isinstance(response, dict) or response.get("id") is None:
        raise ValueError("cannot attach DeepSeek metadata without a model response")
    updated = copy.deepcopy(record)
    updated["provider_response_metadata"] = metadata
    group = EvidenceGroup(str(updated["group"]))
    store.write(str(updated["case_id"]), group, str(updated["cache_key"]), updated)
    persisted = store.load(str(updated["case_id"]), group, str(updated["cache_key"]))
    if persisted is None:
        raise OSError("DeepSeek artifact metadata was not persisted")
    return persisted
