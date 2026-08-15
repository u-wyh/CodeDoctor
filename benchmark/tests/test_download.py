"""Unit tests for official Codeflaws metadata parsing."""

import tempfile
import unittest
from pathlib import Path

from benchmark.scripts.download_codeflaws import DefectTableParser, _download


class DefectTableParserTests(unittest.TestCase):
    def test_extracts_table_cells(self) -> None:
        parser = DefectTableParser()
        parser.feed(
            "<table><tr><td>1-A-bug-10-11</td><td>DCCR</td>"
            "<td>WRONG_ANSWER</td><td>-</td></tr></table>"
        )
        self.assertEqual(
            [["1-A-bug-10-11", "DCCR", "WRONG_ANSWER", "-"]],
            parser.rows,
        )

    def test_existing_archive_is_reused_without_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "codeflaws.tar.gz"
            archive.write_bytes(b"already downloaded")
            record = _download("https://invalid.example/archive", archive)

        self.assertTrue(record["reused_existing_archive"])
        self.assertFalse(record["resumed"])
        self.assertEqual(len(b"already downloaded"), record["size_bytes"])


if __name__ == "__main__":
    unittest.main()
