"""Docker integration tests for ASan/UBSan analysis mode."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from analysis.sanitizer.analyzer import analyze_program
from sandbox.runner import RunnerConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"


class SanitizerIntegrationTests(unittest.TestCase):
    def analyze(self, name: str):
        directory = EXAMPLES / name
        return analyze_program(
            directory / "main.cpp",
            directory / "input.txt",
            RunnerConfig(run_timeout_seconds=5.0),
        )

    def assert_detected(
        self,
        example: str,
        analyzer: str,
        category: str,
        expected_line: int,
        expected_function: str = "main",
    ):
        result = self.analyze(example)
        matches = [
            item
            for item in result.evidence
            if item.analyzer == analyzer and item.category == category
        ]
        self.assertTrue(
            matches,
            f"missing {analyzer}/{category}: "
            f"{[item.to_dict() for item in result.evidence]}",
        )
        item = matches[0]
        self.assertEqual("main.cpp", item.location.file)
        self.assertEqual(expected_line, item.location.line)
        self.assertEqual(expected_function, item.function)
        json.dumps(result.to_dict())
        return result, item

    def test_clean_program_has_no_evidence(self) -> None:
        result = self.analyze("sanitizer_clean")
        self.assertEqual([], result.evidence)
        self.assertEqual("success", result.runner.status.value)
        self.assertEqual(0, result.to_dict()["analysis"]["evidence_count"])

    def test_heap_buffer_overflow(self) -> None:
        _, item = self.assert_detected(
            "asan_heap_overflow", "asan", "heap-buffer-overflow", 4
        )
        self.assertEqual("WRITE", item.memory_access.operation)
        self.assertEqual(4, item.memory_access.size)

    def test_stack_buffer_overflow(self) -> None:
        self.assert_detected(
            "asan_stack_overflow", "asan", "stack-buffer-overflow", 4
        )

    def test_heap_use_after_free(self) -> None:
        _, item = self.assert_detected(
            "asan_use_after_free", "asan", "heap-use-after-free", 4
        )
        self.assertEqual("READ", item.memory_access.operation)

    def test_double_free(self) -> None:
        self.assert_detected(
            "asan_double_free", "asan", "double-free", 2, "release(int*)"
        )

    def test_memory_leak(self) -> None:
        self.assert_detected(
            "asan_memory_leak", "lsan", "memory-leak", 2, "leak_memory()"
        )

    def test_signed_integer_overflow(self) -> None:
        self.assert_detected(
            "ubsan_signed_overflow", "ubsan", "signed-integer-overflow", 5
        )

    def test_division_by_zero(self) -> None:
        self.assert_detected(
            "ubsan_division_by_zero", "ubsan", "division-by-zero", 3
        )

    def test_invalid_shift(self) -> None:
        self.assert_detected(
            "ubsan_invalid_shift", "ubsan", "invalid-shift", 3
        )

    def test_null_pointer_access(self) -> None:
        self.assert_detected(
            "ubsan_null_pointer", "ubsan", "null-pointer-access", 3
        )

    def test_analysis_cli_outputs_structured_json(self) -> None:
        directory = EXAMPLES / "ubsan_signed_overflow"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "sandbox.runner.main",
                str(directory / "main.cpp"),
                str(directory / "input.txt"),
                "--analysis",
                "sanitizer",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual("sanitizer", payload["analysis"]["mode"])
        self.assertEqual(1, payload["analysis"]["evidence_count"])
        self.assertEqual(
            "signed-integer-overflow",
            payload["analysis"]["evidence"][0]["category"],
        )


if __name__ == "__main__":
    unittest.main()
