"""Verify the frozen Phase 9 patch corpus without writing it."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import PHASE9_PATCH_CORPUS  # noqa: E402
from benchmark.frozen_artifacts import FrozenArtifactError  # noqa: E402
from validation_phase9.corpus import build_formal_patch_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    value = build_formal_patch_corpus()
    if not PHASE9_PATCH_CORPUS.is_file():
        raise FrozenArtifactError(
            "Required frozen artifact missing: Phase 9 patch corpus. "
            "Frozen outputs were not modified."
        )
    frozen = json.loads(PHASE9_PATCH_CORPUS.read_text(encoding="utf-8"))
    if value != frozen:
        raise FrozenArtifactError(
            "Frozen artifact hash mismatch: computed Phase 9 patch corpus does not "
            "match the tracked manifest. Frozen outputs were not modified."
        )
    print(
        f"verified patches={value['patch_count']} cases={value['case_count']} "
        f"hash={value['overall_manifest_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
