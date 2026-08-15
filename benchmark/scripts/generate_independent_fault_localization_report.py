"""Generate the Phase 6 independent fault-localization report."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import FAULT_LOCALIZATION_INDEPENDENT_REPORT  # noqa: E402
from fault_localization.independent_reporting import (  # noqa: E402
    write_independent_report,
)


if __name__ == "__main__":
    result = write_independent_report()
    print(
        f"wrote {FAULT_LOCALIZATION_INDEPENDENT_REPORT} for "
        f"{result['dataset']['evaluation_cases']} cases"
    )
