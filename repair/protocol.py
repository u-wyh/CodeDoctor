"""Validate that the registered repair-v2 experiment implementation is unchanged."""

import hashlib
import json
from typing import Any

from benchmark.config import PROJECT_ROOT, REPAIR_PROTOCOL


UNCONFIRMED_ONLINE_CALL_LIMITS = {
    "deepseek": 3,
    "openai-compatible": 9,
}


def unconfirmed_online_call_limit(provider: str) -> int | None:
    return UNCONFIRMED_ONLINE_CALL_LIMITS.get(provider)


def bulk_confirmation_required(
    provider: str, expected_calls: int, confirmed: bool
) -> bool:
    limit = unconfirmed_online_call_limit(provider)
    return limit is not None and expected_calls > limit and not confirmed


def validate_repair_protocol() -> dict[str, Any]:
    protocol = json.loads(REPAIR_PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "repair-v2":
        raise ValueError("unsupported repair protocol version")
    for relative, expected in protocol["frozen_implementation"].items():
        actual = hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"repair-v2 implementation hash mismatch for {relative}: "
                f"expected {expected}, got {actual}"
            )
    return protocol
