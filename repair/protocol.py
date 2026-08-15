"""Validate that the registered repair-v1 experiment implementation is unchanged."""

import hashlib
import json
from typing import Any

from benchmark.config import PROJECT_ROOT, REPAIR_PROTOCOL


def validate_repair_protocol() -> dict[str, Any]:
    protocol = json.loads(REPAIR_PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "repair-v1":
        raise ValueError("unsupported repair protocol version")
    for relative, expected in protocol["frozen_implementation"].items():
        actual = hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"repair-v1 implementation hash mismatch for {relative}: "
                f"expected {expected}, got {actual}"
            )
    return protocol
