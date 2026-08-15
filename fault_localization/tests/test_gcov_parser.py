"""Tests for structured gcov JSON parsing."""

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from fault_localization.gcov_parser import parse_gcov_json


class GcovParserTests(unittest.TestCase):
    def test_keeps_unexecuted_executable_lines(self) -> None:
        document = {
            "gcc_version": "12.2.0",
            "files": [
                {
                    "file": "main.c",
                    "lines": [
                        {"line_number": 3, "count": 1},
                        {"line_number": 4, "count": 0},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.gcov.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as output:
                json.dump(document, output)
            coverage = parse_gcov_json(path, "main.c")

        self.assertEqual("12.2.0", coverage.gcc_version)
        self.assertEqual((3, 4), coverage.executable_lines)
        self.assertEqual((3,), coverage.covered_lines)

    def test_parses_real_gcc_branch_records(self) -> None:
        fixture = (
            Path(__file__).parent / "fixtures" / "gcc12_branch.gcov.json"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.gcov.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as output:
                output.write(fixture.read_text(encoding="utf-8"))
            coverage = parse_gcov_json(path, "sample.c")

        self.assertEqual(2, len(coverage.branches))
        self.assertEqual((2, 0, 0, False), (
            coverage.branches[0].line,
            coverage.branches[0].branch_index,
            coverage.branches[0].count,
            coverage.branches[0].taken,
        ))
        self.assertEqual((2, 1, 1, True), (
            coverage.branches[1].line,
            coverage.branches[1].branch_index,
            coverage.branches[1].count,
            coverage.branches[1].taken,
        ))


if __name__ == "__main__":
    unittest.main()
