"""Capture one manifest-ordered buggy observation per Repair Pilot repair test."""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    RUNTIME_EVIDENCE_MANIFEST,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.protocol import validate_repair_protocol  # noqa: E402
from repair.runtime_evidence import freeze_runtime_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    validate_repair_protocol()
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    frozen = freeze_runtime_evidence(cases, force=args.force)
    print(
        f"wrote {RUNTIME_EVIDENCE_MANIFEST}; "
        f"cases={frozen.validation['case_count']}; "
        f"repair_tests={frozen.validation['repair_test_count']}; "
        f"manifest_hash={frozen.validation['manifest_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
