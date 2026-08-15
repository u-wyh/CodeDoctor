"""Generate SBFL Pilot metrics and report from actual saved artifacts."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fault_localization.reporting import write_report  # noqa: E402


if __name__ == "__main__":
    result = write_report()
    print(
        json.dumps(
            {
                "pilot_cases": result["pilot_cases"],
                "participating_cases": result["participating_cases"],
                "metrics": result["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )
