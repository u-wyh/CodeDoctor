"""Estimate Phase 7 calls/tokens and write the mandatory pre-experiment report."""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import REPAIR_PRE_EXPERIMENT_REPORT  # noqa: E402
from repair.pre_experiment import write_pre_experiment_report  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual-inspection",
        choices=["pending", "passed", "failed"],
        default="pending",
    )
    args = parser.parse_args()
    result = write_pre_experiment_report(args.manual_inspection)
    print(
        f"wrote {REPAIR_PRE_EXPERIMENT_REPORT}; primary calls="
        f"{result['calls']['primary']}"
    )
