"""Generate the Codeflaws pilot report from actual validation artifacts."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.reporting import write_report  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(write_report(), indent=2, sort_keys=True))
