"""Deterministic Phase 8 Base/Feedback/Hidden test partitioning."""

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from benchmark.models import BenchmarkCase, BenchmarkTest


PARTITION_VERSION = "phase8_test_partition_v1"


@dataclass(frozen=True)
class TestPartition:
    case_id: str
    base_tests: tuple[BenchmarkTest, ...]
    feedback_tests: tuple[BenchmarkTest, ...]
    hidden_tests: tuple[BenchmarkTest, ...]
    derived_seed_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "base_tests": [asdict(item) for item in self.base_tests],
            "case_id": self.case_id,
            "derived_seed_sha256": self.derived_seed_sha256,
            "feedback_tests": [asdict(item) for item in self.feedback_tests],
            "hidden_tests": [asdict(item) for item in self.hidden_tests],
        }


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_partition(case: BenchmarkCase, seed: int) -> TestPartition:
    validation = list(case.tests.validation_tests)
    if len(validation) < 2:
        raise ValueError(f"Phase 8 requires at least two validation tests: {case.case_id}")
    seed_bytes = hashlib.sha256(f"{seed}\0{case.case_id}".encode()).digest()
    indices = list(range(len(validation)))
    random.Random(int.from_bytes(seed_bytes, "big")).shuffle(indices)
    feedback_count = min(max(1, len(validation) // 4), len(validation) - 1)
    feedback_indices = set(indices[:feedback_count])
    scoped_validation = [
        BenchmarkTest(
            f"phase8_validation_{index:04d}_{test.test_id}",
            test.input_path,
            test.expected_output_path,
        )
        for index, test in enumerate(validation)
    ]
    return TestPartition(
        case_id=case.case_id,
        base_tests=case.tests.repair_tests,
        feedback_tests=tuple(
            test
            for index, test in enumerate(scoped_validation)
            if index in feedback_indices
        ),
        hidden_tests=tuple(
            test
            for index, test in enumerate(scoped_validation)
            if index not in feedback_indices
        ),
        derived_seed_sha256=seed_bytes.hex(),
    )


def partitioned_case(case: BenchmarkCase, partition: TestPartition) -> BenchmarkCase:
    value = case.to_dict()
    value["tests"] = {
        "repair_tests": [
            asdict(item) for item in (*partition.base_tests, *partition.feedback_tests)
        ],
        "validation_tests": [asdict(item) for item in partition.hidden_tests],
    }
    value["metadata"]["phase8"] = {
        "base_test_ids": [item.test_id for item in partition.base_tests],
        "feedback_test_ids": [item.test_id for item in partition.feedback_tests],
        "hidden_test_ids": [item.test_id for item in partition.hidden_tests],
        "partition_version": PARTITION_VERSION,
    }
    return BenchmarkCase.from_dict(value)


def partition_manifest(cases: Sequence[BenchmarkCase], seed: int) -> dict[str, object]:
    records = [derive_partition(case, seed).to_dict() for case in cases]
    value: dict[str, object] = {
        "case_count": len(records),
        "partitions": records,
        "protocol_version": PARTITION_VERSION,
        "seed": seed,
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def load_partition_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.get("overall_manifest_hash")
    unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
    if claimed != canonical_hash(unsigned):
        raise ValueError("Phase 8 test-partition manifest hash mismatch")
    if value.get("protocol_version") != PARTITION_VERSION:
        raise ValueError("Phase 8 test-partition version mismatch")
    return value


def second_round_order(case_id: str, seed: int) -> tuple[str, str]:
    digest = hashlib.sha256(f"{seed}\0{case_id}".encode()).digest()
    return ("retry_control", "feedback") if digest[-1] & 1 == 0 else (
        "feedback",
        "retry_control",
    )
