"""Small OpenAI-compatible chat-completions provider and deterministic fakes."""

import json
import socket
import urllib.error
import urllib.request
from typing import Protocol

from .models import ModelParameters, ModelResponse, PromptDocument


class ModelError(RuntimeError):
    pass


class ModelTimeout(ModelError):
    pass


class ModelAPIError(ModelError):
    pass


class MalformedModelResponse(ModelError):
    pass


class RepairModel(Protocol):
    parameters: ModelParameters

    def generate(self, prompt: PromptDocument) -> ModelResponse: ...


class OpenAICompatibleProvider:
    def __init__(self, parameters: ModelParameters, api_key: str):
        if not api_key:
            raise ValueError("API key is required")
        self.parameters = parameters
        self._api_key = api_key

    def generate(self, prompt: PromptDocument) -> ModelResponse:
        payload: dict[str, object] = {
            "model": self.parameters.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": self.parameters.temperature,
            "max_tokens": self.parameters.max_tokens,
        }
        if self.parameters.seed is not None:
            payload["seed"] = self.parameters.seed
        url = self.parameters.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
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
            raise ModelTimeout("model request timed out") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise ModelAPIError(f"model API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ModelAPIError(f"model API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MalformedModelResponse("model API returned invalid JSON") from exc
        try:
            choice = document["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("content is not text")
            return ModelResponse(
                text=content,
                response_id=document.get("id"),
                finish_reason=choice.get("finish_reason"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedModelResponse(
                "model API response does not contain choices[0].message.content"
            ) from exc


class FakeRepairModel:
    """Deterministic test/smoke provider; never contributes experimental metrics."""

    def __init__(self, parameters: ModelParameters, response: str):
        self.parameters = parameters
        self.response = response
        self.calls = 0
        self.error: ModelError | None = None

    def generate(self, prompt: PromptDocument) -> ModelResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ModelResponse(self.response, response_id=f"fake-{self.calls}")


class FakeEchoRepairModel:
    """Smoke provider that returns the buggy source unchanged."""

    def __init__(self, parameters: ModelParameters):
        self.parameters = parameters
        self.calls = 0

    def generate(self, prompt: PromptDocument) -> ModelResponse:
        from .extraction import extract_source

        self.calls += 1
        extracted = extract_source(prompt.user)
        if extracted.source is None:
            raise MalformedModelResponse("fake could not recover source from prompt")
        return ModelResponse(
            text=f"```cpp\n{extracted.source}```\n",
            response_id=f"fake-echo-{self.calls}",
        )
