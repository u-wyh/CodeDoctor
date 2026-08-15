"""Load and verify the preregistered FL-v1 implementation."""

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmark.config import PROJECT_ROOT


METHOD_PATH = PROJECT_ROOT / "benchmark" / "metadata" / "fl_method_v1.json"


def validate_frozen_method(path: Path = METHOD_PATH) -> dict[str, Any]:
    method = json.loads(path.read_text(encoding="utf-8"))
    if method.get("method_version") != "fl-v1":
        raise ValueError("expected frozen method_version fl-v1")
    for relative, expected in method.get("implementation", {}).items():
        implementation = PROJECT_ROOT / relative
        actual = hashlib.sha256(implementation.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"frozen implementation mismatch for {relative}: "
                f"expected {expected}, got {actual}"
            )
    return method
