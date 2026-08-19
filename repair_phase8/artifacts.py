"""Secret-free content-addressed Phase 8 artifact storage."""

import hashlib
import json
from pathlib import Path
from typing import Any

from repair.models import ModelParameters

from .models import Phase8Arm, Phase8Prompt


def phase8_cache_key(
    case_id: str,
    arm: Phase8Arm,
    prompt: Phase8Prompt,
    parameters: ModelParameters,
    partition_hash: str,
    first_patch_hash: str | None = None,
) -> str:
    value = {
        "arm": arm.value,
        "case_id": case_id,
        "first_patch_hash": first_patch_hash,
        "model_parameters": parameters.cache_view(),
        "partition_hash": partition_hash,
        "prompt_hash": prompt.prompt_hash,
        "template_version": prompt.template_version,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Phase8ArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def path_for(self, arm: Phase8Arm, case_id: str, key: str) -> Path:
        return self.root / arm.value / case_id / f"{key}.json"

    def load(
        self, arm: Phase8Arm, case_id: str, key: str
    ) -> dict[str, Any] | None:
        path = self.path_for(arm, case_id, key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write(
        self,
        arm: Phase8Arm,
        case_id: str,
        key: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        path = self.path_for(arm, case_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        return json.loads(path.read_text(encoding="utf-8"))
