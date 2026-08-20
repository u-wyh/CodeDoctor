"""Freeze the formal Phase 9 patch corpus without executing patches."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import PHASE9_PATCH_CORPUS  # noqa: E402
from validation_phase9.corpus import build_formal_patch_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    value = build_formal_patch_corpus()
    PHASE9_PATCH_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    PHASE9_PATCH_CORPUS.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"patches={value['patch_count']} cases={value['case_count']} "
        f"hash={value['overall_manifest_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
