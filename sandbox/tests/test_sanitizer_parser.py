"""Regression tests for structured sanitizer report parsing."""

import json
import unittest
from pathlib import Path

from analysis.sanitizer.parser import SanitizerParser


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class SanitizerParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = SanitizerParser()

    def fixture(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    def test_parses_asan_category_access_location_and_stack(self) -> None:
        report = self.fixture("asan_heap_buffer_overflow.txt")
        evidence = self.parser.parse(report)

        self.assertEqual(1, len(evidence))
        item = evidence[0]
        self.assertEqual("asan", item.analyzer)
        self.assertEqual("heap-buffer-overflow", item.category)
        self.assertEqual("main.cpp", item.location.file)
        self.assertEqual(8, item.location.line)
        self.assertEqual(19, item.location.column)
        self.assertEqual("write_past_end", item.function)
        self.assertEqual("WRITE", item.memory_access.operation)
        self.assertEqual(4, item.memory_access.size)
        self.assertEqual(3, len(item.stack_trace))
        self.assertTrue(item.stack_trace[0].is_user_code)
        self.assertFalse(item.stack_trace[2].is_user_code)
        self.assertEqual(report, item.raw_report)

    def test_parses_multiple_ubsan_diagnostics(self) -> None:
        report = self.fixture("ubsan_multiple.txt")
        evidence = self.parser.parse(report)

        self.assertEqual(2, len(evidence))
        self.assertEqual("signed-integer-overflow", evidence[0].category)
        self.assertEqual("overflow", evidence[0].function)
        self.assertEqual(6, evidence[0].location.line)
        self.assertEqual("invalid-shift", evidence[1].category)
        self.assertEqual(10, evidence[1].location.line)
        self.assertEqual("main.cpp", evidence[1].location.file)

    def test_unknown_asan_category_preserves_raw_report(self) -> None:
        report = (
            "==7==ERROR: AddressSanitizer: unexpected sanitizer condition\n"
            "    #0 0x1234 in main /workspace/main.cpp:4:2\n"
        )
        evidence = self.parser.parse(report)

        self.assertEqual(1, len(evidence))
        self.assertEqual("unknown", evidence[0].category)
        self.assertEqual(report, evidence[0].raw_report)

    def test_empty_and_unrelated_stderr_produce_no_evidence(self) -> None:
        self.assertEqual([], self.parser.parse(""))
        self.assertEqual([], self.parser.parse("ordinary application error\n"))

    def test_incomplete_deadly_signal_report_is_not_lost(self) -> None:
        report = "AddressSanitizer:DEADLYSIGNAL\n" * 3
        evidence = self.parser.parse(report)

        self.assertEqual(1, len(evidence))
        self.assertEqual("asan", evidence[0].analyzer)
        self.assertEqual("unknown", evidence[0].category)
        self.assertEqual(report, evidence[0].raw_report)

    def test_evidence_is_json_serializable(self) -> None:
        evidence = self.parser.parse(
            self.fixture("asan_heap_buffer_overflow.txt")
        )
        serialized = json.dumps([item.to_dict() for item in evidence])
        self.assertIn("heap-buffer-overflow", serialized)


if __name__ == "__main__":
    unittest.main()
