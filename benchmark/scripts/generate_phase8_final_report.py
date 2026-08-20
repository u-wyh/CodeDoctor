"""Validate Stage 2 artifacts and generate the final Phase 8 report."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE8_FINAL_REPORT,
    PHASE8_STAGE2_PROMPT_AUDIT,
    PHASE8_STAGE2_RESULT_MANIFEST,
)
from repair_phase8.partition import canonical_hash  # noqa: E402
from repair_phase8.protocol import validate_phase8_preflight, validate_stage2_gate  # noqa: E402
from repair_phase8.stage2_reporting import (  # noqa: E402
    build_stage2_result_manifest,
    render_final_report,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    preflight = validate_phase8_preflight()
    gate = validate_stage2_gate()
    prompt_audit = json.loads(PHASE8_STAGE2_PROMPT_AUDIT.read_text(encoding="utf-8"))
    value = build_stage2_result_manifest(
        preflight["cases"], gate["stage1"], gate["cohort"], prompt_audit
    )
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    if value["overall_manifest_hash"] != canonical_hash(unsigned):
        raise ValueError("Stage 2 result manifest hash mismatch")
    _write(PHASE8_STAGE2_RESULT_MANIFEST, json.dumps(value, indent=2, sort_keys=True) + "\n")
    _write(PHASE8_FINAL_REPORT, render_final_report(value))
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
