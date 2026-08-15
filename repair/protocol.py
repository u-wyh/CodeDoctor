"""Validate that the registered repair-v2 experiment implementation is unchanged."""

import hashlib
import json
from typing import Any

from benchmark.config import PROJECT_ROOT, REPAIR_PROTOCOL


BULK_ONLINE_CALL_THRESHOLD = 9


def bulk_confirmation_required(
    provider: str, expected_calls: int, confirmed: bool
) -> bool:
    return (
        provider == "openai-compatible"
        and expected_calls > BULK_ONLINE_CALL_THRESHOLD
        and not confirmed
    )


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
