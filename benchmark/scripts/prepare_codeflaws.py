"""Convert the extracted Codeflaws layout into CodeDoctor manifest JSONL."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.codeflaws import (  # noqa: E402
    discover_case_directories,
    find_benchmark_root,
    parse_case_directory,
)
from benchmark.config import (  # noqa: E402
    CODEFLAWS_CLASSIFICATION,
    CODEFLAWS_MANIFEST,
)


def main() -> int:
    if not CODEFLAWS_CLASSIFICATION.exists():
        print(
            f"classification metadata not found: {CODEFLAWS_CLASSIFICATION}",
            file=sys.stderr,
        )
        return 1

    classification_document = json.loads(
        CODEFLAWS_CLASSIFICATION.read_text(encoding="utf-8")
    )
    classifications = classification_document["cases"]
    try:
        benchmark_root = find_benchmark_root()
    except FileNotFoundError as exc:
        print(f"prepare_codeflaws: {exc}", file=sys.stderr)
        return 1

    directories = discover_case_directories(benchmark_root)
    cases = [parse_case_directory(path, classifications) for path in directories]
    CODEFLAWS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = CODEFLAWS_MANIFEST.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as manifest:
        for case in cases:
            manifest.write(json.dumps(case.to_dict(), sort_keys=True) + "\n")
    temporary.replace(CODEFLAWS_MANIFEST)

    unknown_classes = sum(
        case.metadata["defect_class"] == "unknown" for case in cases
    )
    print(
        json.dumps(
            {
                "benchmark_root": benchmark_root.as_posix(),
                "manifest": CODEFLAWS_MANIFEST.as_posix(),
                "parsed_cases": len(cases),
                "unknown_defect_classes": unknown_classes,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
