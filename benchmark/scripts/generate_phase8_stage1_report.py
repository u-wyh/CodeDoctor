"""Generate the offline Phase 8 Stage 1 report and Stage 2 prompt audit."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    DEEPSEEK_FORMAL_PRICING_SNAPSHOT,
    PHASE8_STAGE1_REPORT,
    PHASE8_STAGE2_PROMPT_AUDIT,
)
from repair_phase8.partition import canonical_hash  # noqa: E402
from repair_phase8.protocol import validate_phase8_preflight, validate_stage2_gate  # noqa: E402
from repair_phase8.reporting import (  # noqa: E402
    build_stage1_summary,
    build_stage2_prompt_audit,
    load_initial_records,
    render_stage1_report,
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
    first = build_stage2_prompt_audit(preflight, gate["stage1"], gate["cohort"])
    second = build_stage2_prompt_audit(preflight, gate["stage1"], gate["cohort"])
    first_unsigned = {key: value for key, value in first.items() if key != "overall_manifest_hash"}
    if first != second or first["overall_manifest_hash"] != canonical_hash(first_unsigned):
        raise ValueError("Stage 2 prompt audit is not reproducible")
    if first["operational_size_gate"]["status"] != "passed":
        raise ValueError("Stage 2 prompt payload hard gate failed")
    records = load_initial_records(preflight["cases"], gate["stage1"])
    summary = build_stage1_summary(records, gate["stage1"], gate["cohort"], first)
    pricing = json.loads(DEEPSEEK_FORMAL_PRICING_SNAPSHOT.read_text(encoding="utf-8"))
    _write(PHASE8_STAGE2_PROMPT_AUDIT, json.dumps(first, indent=2, sort_keys=True) + "\n")
    _write(PHASE8_STAGE1_REPORT, render_stage1_report(summary, first, pricing))
    print(json.dumps({"prompt_audit": first, "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
