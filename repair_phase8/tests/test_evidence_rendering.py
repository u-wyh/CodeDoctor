import hashlib
import json
import unittest

from benchmark.config import PHASE8_RENDER_PROTOCOL
from repair.models import RepairTestEvidence
from repair_phase8.evidence_rendering import (
    RENDER_PROTOCOL_VERSION,
    COMPILER_FULL_BYTES,
    MISMATCH_CONTEXT_AFTER_BYTES,
    MISMATCH_CONTEXT_BEFORE_BYTES,
    ORACLE_FULL_BYTES,
    STDERR_FULL_BYTES,
    STDOUT_FULL_BYTES,
    first_differing_byte,
    render_execution_evidence,
    render_failed_feedback,
)


TEN_MB = 10 * 1024 * 1024


def observation(
    stdout: str,
    stderr: str = "",
    *,
    verdict: str = "FAIL",
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> RepairTestEvidence:
    return RepairTestEvidence("test", verdict, stdout, stderr, exit_code, timed_out)


def render(item: RepairTestEvidence, expected: str = "expected"):
    return render_execution_evidence(
        (item,), {"test": expected}, heading="## Evidence"
    )


class EvidenceRenderingTests(unittest.TestCase):
    def test_frozen_protocol_matches_implementation_constants(self) -> None:
        protocol = json.loads(PHASE8_RENDER_PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual(RENDER_PROTOCOL_VERSION, protocol["protocol_version"])
        self.assertEqual(ORACLE_FULL_BYTES, protocol["common_oracle"]["full_field_bytes"])
        self.assertEqual(STDOUT_FULL_BYTES, protocol["execution_stdout"]["abnormal_full_bytes"])
        self.assertEqual(STDERR_FULL_BYTES, protocol["stderr"]["full_bytes"])
        self.assertEqual(COMPILER_FULL_BYTES, protocol["compiler_stderr"]["full_bytes"])
        self.assertEqual(
            MISMATCH_CONTEXT_BEFORE_BYTES,
            protocol["execution_stdout"]["mismatch_context_before_bytes"],
        )
        self.assertEqual(
            MISMATCH_CONTEXT_AFTER_BYTES,
            protocol["execution_stdout"]["mismatch_context_after_bytes"],
        )

    def test_10mb_stdout_pass_is_deduplicated(self) -> None:
        value = "x" * TEN_MB
        result = render(observation(value, verdict="PASS"), value)
        self.assertLess(len(result.text.encode()), 2000)
        self.assertIn("matches expected output exactly", result.text)
        self.assertIn(f"stdout_bytes: {TEN_MB}", result.text)
        self.assertIn(hashlib.sha256(value.encode()).hexdigest(), result.text)

    def test_10mb_stdout_mismatch_has_fixed_first_difference_window(self) -> None:
        expected = "a" * TEN_MB
        actual = expected[: TEN_MB // 2] + "b" + expected[TEN_MB // 2 + 1 :]
        result = render(observation(actual), expected)
        self.assertLess(len(result.text.encode()), 7000)
        self.assertIn(f"first_differing_byte_offset: {TEN_MB // 2}", result.text)
        self.assertIn("actual_window_omitted_before_bytes", result.text)
        self.assertIn("actual_window_omitted_after_bytes", result.text)

    def test_10mb_stderr_uses_4096_byte_prefix_and_suffix(self) -> None:
        result = render(observation("expected", "e" * TEN_MB), "expected")
        self.assertLess(len(result.text.encode()), 10000)
        self.assertIn("stderr_truncated: true", result.text)
        self.assertIn(f"stderr_omitted_bytes: {TEN_MB - 8192}", result.text)

    def test_runtime_error_bounds_huge_stdout_and_stderr(self) -> None:
        result = render(
            observation("o" * TEN_MB, "e" * TEN_MB, exit_code=1), "expected"
        )
        self.assertLess(len(result.text.encode()), 15000)
        self.assertIn(f"stdout_omitted_bytes: {TEN_MB - 4096}", result.text)
        self.assertIn(f"stderr_omitted_bytes: {TEN_MB - 8192}", result.text)

    def test_compiler_error_bounds_huge_diagnostics(self) -> None:
        result = render_failed_feedback(
            {"compile": {"exit_code": 1, "stderr": "d" * TEN_MB}, "failed_tests": []}
        )
        self.assertEqual(RENDER_PROTOCOL_VERSION, "phase8-runtime-evidence-render-v2")
        self.assertLess(len(result.text.encode()), 18000)
        self.assertIn(f"compiler_stderr_omitted_bytes: {TEN_MB - 16384}", result.text)

    def test_utf8_multibyte_boundary_has_stable_replace_policy(self) -> None:
        value = "a" * 2047 + "€" + "z" * 4096
        first = render(observation(value, exit_code=1))
        second = render(observation(value, exit_code=1))
        self.assertEqual(first, second)
        self.assertIn("�", first.text)

    def test_empty_stdout_and_stderr_are_supported(self) -> None:
        result = render(observation("", "", exit_code=1), "")
        self.assertIn("stdout_bytes: 0", result.text)
        self.assertIn("stderr_bytes: 0", result.text)
        self.assertIn("stdout_truncated: false", result.text)

    def test_one_byte_mismatch_near_beginning(self) -> None:
        result = render(observation("xbc"), "abc")
        self.assertIn("first_differing_byte_offset: 0", result.text)
        self.assertEqual(0, first_differing_byte(b"abc", b"xbc"))

    def test_mismatch_near_end(self) -> None:
        expected = "a" * 5000 + "x"
        actual = "a" * 5000 + "y"
        result = render(observation(actual), expected)
        self.assertIn("first_differing_byte_offset: 5000", result.text)
        self.assertIn("actual_window_omitted_before_bytes: 3976", result.text)

    def test_length_only_mismatch_uses_common_prefix_length(self) -> None:
        result = render(observation("abc"), "abcd")
        self.assertIn("first_differing_byte_offset: 3", result.text)
        self.assertEqual(3, first_differing_byte(b"abcd", b"abc"))


if __name__ == "__main__":
    unittest.main()
