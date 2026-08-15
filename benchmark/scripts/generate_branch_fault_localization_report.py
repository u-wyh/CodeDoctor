"""Generate the Phase 5 branch-aware fault-localization report."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fault_localization.branch_reporting import write_branch_report  # noqa: E402


if __name__ == "__main__":
    result = write_branch_report()
    print(
        json.dumps(
            {
                "pilot_cases": result["pilot_cases"],
                "repair_tests": result["repair_tests"],
                "metrics": result["metrics"],
                "tie_statistics": result["tie_statistics"],
            },
            indent=2,
            sort_keys=True,
        )
    )
