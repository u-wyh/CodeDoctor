"""Secret-free content-addressed storage for expensive model calls."""

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import EvidenceGroup, ModelParameters, PromptDocument


def cache_key(
    case_id: str,
    group: EvidenceGroup,
    prompt: PromptDocument,
    parameters: ModelParameters,
) -> str:
    value = {
        "case_id": case_id,
        "group": group.value,
        "model_parameters": parameters.cache_view(),
        "prompt_hash": prompt.prompt_hash,
        "template_version": prompt.template_version,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def path_for(self, case_id: str, group: EvidenceGroup, key: str) -> Path:
        return self.root / case_id / group.value / f"{key}.json"

    def load(self, case_id: str, group: EvidenceGroup, key: str) -> dict[str, Any] | None:
        path = self.path_for(case_id, group, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(
        self, case_id: str, group: EvidenceGroup, key: str, value: dict[str, Any]
    ) -> Path:
        path = self.path_for(case_id, group, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
        return path
