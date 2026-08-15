"""Parse GCC gcov JSON without depending on human-readable text output."""

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

from .models import BranchCoverage


@dataclass(frozen=True)
class GcovCoverage:
    gcc_version: str
    executable_lines: tuple[int, ...]
    covered_lines: tuple[int, ...]
    branches: tuple[BranchCoverage, ...]


def parse_gcov_json(path: Path, source_name: str) -> GcovCoverage:
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
    branches = tuple(
        BranchCoverage(
            line=int(line["line_number"]),
            branch_index=index,
            count=int(branch.get("count", 0)),
            taken=int(branch.get("count", 0)) > 0,
            fallthrough=bool(branch.get("fallthrough", False)),
            throw=bool(branch.get("throw", False)),
        )
        for line in lines
        for index, branch in enumerate(line.get("branches", []))
    )
    return GcovCoverage(
        gcc_version=str(document.get("gcc_version", "unknown")),
        executable_lines=executable,
        covered_lines=covered,
        branches=branches,
    )
