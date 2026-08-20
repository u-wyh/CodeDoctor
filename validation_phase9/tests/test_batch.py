"""Batch metadata parsing and sanitizer finding tests."""

import base64
import hashlib
import unittest

from validation_phase9.batch import parse_batch_output


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


class BatchTests(unittest.TestCase):
    def test_parses_clean_timeout_and_sanitizer_observations(self) -> None:
        empty = hashlib.sha256(b"").hexdigest()
        ubsan = "main.c:1:2: runtime error: signed integer overflow"
        output = "\n".join(
            (
                f"COMPILE\t0\t{empty}\t{empty}\t0\t",
                f"RUN\t0\t0\tfalse\t{empty}\t0\t{empty}\t0\t\t3",
                f"RUN\t1\t124\ttrue\t{empty}\t0\t{empty}\t{len(ubsan)}\t{encoded(ubsan)}\t5001",
            )
        )
        value = parse_batch_output(output, ["clean", "timeout"], 10)
        self.assertTrue(value.compile_success)
        self.assertFalse(value.observations[0].timed_out)
        self.assertTrue(value.observations[1].timed_out)
        self.assertEqual(("ubsan",), value.observations[1].sanitizer_findings)

    def test_missing_observation_is_rejected(self) -> None:
        empty = hashlib.sha256(b"").hexdigest()
        with self.assertRaisesRegex(ValueError, "every requested"):
            parse_batch_output(f"COMPILE\t0\t{empty}\t{empty}\t0\t", ["x"], 1)


if __name__ == "__main__":
    unittest.main()
