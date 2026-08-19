"""Capture one buggy observation for every Phase 8 public repair-time test."""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE8_EVALUATION_SET,
    PHASE8_RUNTIME_MANIFEST,
)
from benchmark.models import load_manifest  # noqa: E402
from repair_phase8.runtime_evidence import freeze_phase8_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    if len(cases) != 100:
        parser.error(f"Phase 8 Evaluation Set must contain 100 cases, got {len(cases)}")
    frozen = freeze_phase8_runtime(cases, force=args.force)
    print(
        f"wrote {PHASE8_RUNTIME_MANIFEST}; "
        f"cases={frozen.validation['case_count']}; "
        f"repair_tests={frozen.validation['repair_test_count']}; "
        f"manifest_hash={frozen.validation['manifest_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
