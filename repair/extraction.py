"""Conservative extraction of one complete C/C++ source from model output."""

import re

from .models import ExtractionResult


FENCED_CODE = re.compile(
    r"```(?P<language>cpp|c\+\+|c|cc)?\s*\n(?P<code>.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def _looks_like_source(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and (
        "main(" in stripped.replace(" ", "")
        or "main (" in stripped
    ) and ("{" in stripped and "}" in stripped)


def extract_source(response: str) -> ExtractionResult:
    matches = list(FENCED_CODE.finditer(response))
    preferred = [
        match
        for match in matches
        if (match.group("language") or "").lower() in {"cpp", "c++", "c", "cc"}
    ]
    for match in preferred or matches:
        source = match.group("code").strip()
        if _looks_like_source(source):
            return ExtractionResult("success", source + "\n", "fenced_code")
    if not matches and _looks_like_source(response):
        return ExtractionResult("success", response.strip() + "\n", "plain_source")
    return ExtractionResult("invalid_model_output", None, None)
