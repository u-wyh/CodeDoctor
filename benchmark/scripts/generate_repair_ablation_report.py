"""Generate Phase 7 repair evidence-ablation summary and report."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import REPAIR_REPORT  # noqa: E402
from repair.reporting import write_report  # noqa: E402


if __name__ == "__main__":
    result = write_report()
    print(
        f"wrote {REPAIR_REPORT}; online artifacts="
        f"{result['experiment']['online_artifacts']}"
    )
