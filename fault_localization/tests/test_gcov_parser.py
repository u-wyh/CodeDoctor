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
            version, executable, covered = parse_gcov_json(path, "main.c")

        self.assertEqual("12.2.0", version)
        self.assertEqual((3, 4), executable)
        self.assertEqual((3,), covered)


if __name__ == "__main__":
    unittest.main()
