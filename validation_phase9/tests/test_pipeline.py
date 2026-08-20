"""Reference filter, sanitizer, and differential classification tests."""

import hashlib
import unittest

from validation_phase9.batch import BatchObservation, BatchResult
from validation_phase9.mutation import MutationCandidate
from validation_phase9.pipeline import (
    accept_reference_candidates,
    differential_manifest,
    differential_failure_type,
    sanitizer_failure_type,
)


EMPTY = hashlib.sha256(b"").hexdigest()


def observation(
    test_id: str,
    *,
    exit_code: int = 0,
    output_hash: str = EMPTY,
    stderr: str = "",
    timeout: bool = False,
) -> BatchObservation:
    return BatchObservation(
        1,
        exit_code,
        stderr,
        EMPTY,
        len(stderr),
        output_hash,
        0,
        test_id,
        timeout,
    )


def batch(items: list[BatchObservation], compile_exit: int = 0) -> BatchResult:
    return BatchResult(compile_exit, "", EMPTY, 0, tuple(items), 1)


class PipelineTests(unittest.TestCase):
    def test_differential_manifest_hash_is_order_independent(self) -> None:
        records = [
            {
                "accepted": [],
                "case_id": case_id,
                "generator_version": "v1",
                "proposal_count": 0,
                "seed": 20260820,
            }
            for case_id in ("b", "a")
        ]
        self.assertEqual(
            differential_manifest(records)["overall_manifest_hash"],
            differential_manifest(list(reversed(records)))["overall_manifest_hash"],
        )

    def test_reference_filter_rejects_crash_timeout_nondeterminism_and_sanitizer(self) -> None:
        candidates = [
            MutationCandidate(str(index), index, str(index), "seed", index)
            for index in range(5)
        ]
        ids = [f"candidate/{index:06d}" for index in range(5)]
        first = [observation(test_id) for test_id in ids]
        second = [observation(test_id) for test_id in ids]
        sanitized = [observation(test_id) for test_id in ids]
        first[1] = observation(ids[1], exit_code=1)
        first[2] = observation(ids[2], timeout=True, exit_code=124)
        second[3] = observation(ids[3], output_hash="different")
        sanitized[4] = observation(
            ids[4], stderr="main.c:1:1: runtime error: overflow"
        )
        accepted = accept_reference_candidates(
            candidates, batch(first), batch(second), batch(sanitized)
        )
        self.assertEqual(1, len(accepted))
        self.assertEqual(candidates[0].input_hash, accepted[0]["input_hash"])

    def test_reference_sanitizer_compile_failure_excludes_every_candidate(self) -> None:
        candidate = MutationCandidate("0", 0, "h", "s", 0)
        item = observation("candidate/000000")
        self.assertEqual(
            [],
            accept_reference_candidates(
                [candidate], batch([item]), batch([item]), batch([], compile_exit=1)
            ),
        )

    def test_sanitizer_and_differential_failure_types(self) -> None:
        self.assertEqual("sanitizer_timeout", sanitizer_failure_type(observation("x", timeout=True, exit_code=124)))
        self.assertEqual("ASan", sanitizer_failure_type(observation("x", stderr="ERROR: AddressSanitizer: heap-buffer-overflow")))
        self.assertEqual("UBSan", sanitizer_failure_type(observation("x", stderr="main.c:1:1: runtime error: overflow")))
        self.assertEqual("sanitizer_abnormal_exit", sanitizer_failure_type(observation("x", exit_code=1)))
        self.assertIsNone(sanitizer_failure_type(observation("x")))
        self.assertEqual("differential_timeout", differential_failure_type(observation("x", timeout=True, exit_code=124), EMPTY))
        self.assertEqual("differential_runtime_error", differential_failure_type(observation("x", exit_code=2), EMPTY))
        self.assertEqual("differential_output_mismatch", differential_failure_type(observation("x", output_hash="other"), EMPTY))
        self.assertIsNone(differential_failure_type(observation("x"), EMPTY))

    def test_acceptance_cap_is_enforced(self) -> None:
        candidates = [MutationCandidate(str(i), i, str(i), "s", i) for i in range(3)]
        items = [observation(f"candidate/{i:06d}") for i in range(3)]
        self.assertEqual(2, len(accept_reference_candidates(candidates, batch(items), batch(items), batch(items), acceptance_cap=2)))


if __name__ == "__main__":
    unittest.main()
