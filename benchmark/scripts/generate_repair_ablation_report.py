"""Verify the frozen Phase 7 repair summary and report without writing them."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import REPAIR_REPORT  # noqa: E402
from repair.reporting import verify_frozen_report  # noqa: E402


if __name__ == "__main__":
    result = verify_frozen_report()
    print(
        f"verified {REPAIR_REPORT}; online artifacts="
        f"{result['experiment']['online_artifacts']}"
    )
