"""Diagnose runtime instability without changing frozen repair evidence."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.evaluator import evaluate_source  # noqa: E402
from repair.runtime_evidence import (  # noqa: E402
    load_frozen_runtime_evidence,
    runtime_observation_hash,
    runtime_observation_view,
)


def _changed_fields(
    frozen: dict[str, object], observed: dict[str, object]
) -> list[str]:
    changed = []
    frozen_tests = frozen["repair_tests"]
    observed_tests = observed["repair_tests"]
    for before, after in zip(frozen_tests, observed_tests):
        for field in ("stdout", "stderr", "exit_code", "timed_out", "passed"):
            if before[field] != after[field]:
                changed.append(f"{before['test_id']}.{field}")
    return sorted(set(changed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    selected_ids = set(args.case)
    selected = [case for case in cases if case.case_id in selected_ids]
    missing = selected_ids - {case.case_id for case in selected}
    if missing:
        parser.error(f"unknown Repair Pilot cases: {sorted(missing)}")
    frozen = load_frozen_runtime_evidence(cases)
    records = []
    for case in selected:
        baseline = frozen.evaluations[case.case_id]
        frozen_view = runtime_observation_view(baseline)
        frozen_hash = runtime_observation_hash(baseline)
        observed_hashes = []
        changed = set()
        for _ in range(args.runs):
            observed = evaluate_source(
                case, case.get_buggy_source(), include_validation=False
            )
            observed_hashes.append(runtime_observation_hash(observed))
            changed.update(
                _changed_fields(frozen_view, runtime_observation_view(observed))
            )
        records.append(
            {
                "case_id": case.case_id,
                "changed_fields": sorted(changed),
                "frozen_observation_hash": frozen_hash,
                "observed_distinct_hashes": sorted(set(observed_hashes)),
                "observed_runs": args.runs,
                "runtime_nondeterministic": (
                    len(set(observed_hashes)) > 1
                    or any(value != frozen_hash for value in observed_hashes)
                ),
            }
        )
    value = {
        "evaluation_metadata_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_influence": "none",
        "protocol_version": "runtime-nondeterminism-audit-v1",
        "records": records,
        "selection_rule": "diagnostic cases named before audit; no observation selection",
        "snapshot_manifest_hash": frozen.validation["manifest_hash"],
    }
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    value["audit_sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {RUNTIME_EVIDENCE_NONDETERMINISM_AUDIT}; "
        f"cases={len(records)}; runs={args.runs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
