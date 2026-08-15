"""Parse GCC gcov JSON without depending on human-readable text output."""

import gzip
import json
from pathlib import Path


def parse_gcov_json(path: Path, source_name: str) -> tuple[str, tuple[int, ...], tuple[int, ...]]:
    with gzip.open(path, mode="rt", encoding="utf-8") as source:
        document = json.load(source)
    matching = [
        item
        for item in document.get("files", [])
        if Path(item.get("file", "")).name == source_name
    ]
    if len(matching) != 1:
        raise ValueError(
            f"expected one gcov record for {source_name}, found {len(matching)}"
        )
    lines = matching[0].get("lines", [])
    executable = tuple(sorted({int(item["line_number"]) for item in lines}))
    covered = tuple(
        sorted(
            {
                int(item["line_number"])
                for item in lines
                if int(item.get("count", 0)) > 0
            }
        )
    )
    return str(document.get("gcc_version", "unknown")), executable, covered
