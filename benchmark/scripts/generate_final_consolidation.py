"""Generate thesis-facing registries, tables, audits, and freeze metadata."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from final_consolidation.consolidate import generate_final_consolidation  # noqa: E402


def main() -> int:
    result = generate_final_consolidation()
    print(
        json.dumps(
            {
                "audit_status": result["audit"]["status"],
                "dataset_overlap_status": result["datasets"]["status"],
                "final_freeze_status": result["freeze"]["status"],
                "real_llm_calls": result["audit"]["real_llm_calls"],
                "registry_hash": result["registry"]["overall_manifest_hash"],
                "reproducibility_registry_hash": result["reproducibility"]["overall_manifest_hash"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["freeze"]["status"] == "frozen" else 1


if __name__ == "__main__":
    raise SystemExit(main())
