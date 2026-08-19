import unittest

from benchmark.models import (
    BenchmarkCase,
    BenchmarkTest,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)
from repair_phase8.partition import derive_partition, partition_manifest, second_round_order


def make_case(case_id: str = "case-1", validation_count: int = 8) -> BenchmarkCase:
    test = lambda name: BenchmarkTest(name, f"{name}.in", f"{name}.out")
    return BenchmarkCase(
        case_id,
        "test",
        "cpp",
        ProblemIdentity("1", "A"),
        ProgramArtifact("bug.cpp", "bug"),
        ProgramArtifact("ref.cpp", "ref"),
        TestSuites((test("base"),), tuple(test(f"v{i}") for i in range(validation_count))),
        {},
    )


class PartitionTests(unittest.TestCase):
    def test_split_is_deterministic_and_preserves_hidden_tests(self) -> None:
        first = derive_partition(make_case(), 20260820)
        second = derive_partition(make_case(), 20260820)
        self.assertEqual(first, second)
        self.assertEqual(2, len(first.feedback_tests))
        self.assertEqual(6, len(first.hidden_tests))
        self.assertTrue(set(first.feedback_tests).isdisjoint(first.hidden_tests))

    def test_partition_manifest_and_arm_order_are_reproducible(self) -> None:
        cases = [make_case(f"case-{index}", 4) for index in range(20)]
        self.assertEqual(
            partition_manifest(cases, 20260820),
            partition_manifest(cases, 20260820),
        )
        orders = [second_round_order(case.case_id, 20260820) for case in cases]
        self.assertIn(("retry_control", "feedback"), orders)
        self.assertIn(("feedback", "retry_control"), orders)

    def test_fewer_than_two_validation_tests_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            derive_partition(make_case(validation_count=1), 20260820)

    def test_validation_namespace_prevents_base_id_collision(self) -> None:
        case = make_case(validation_count=2)
        value = case.to_dict()
        value["tests"]["validation_tests"][0]["test_id"] = "base"
        partition = derive_partition(BenchmarkCase.from_dict(value), 20260820)
        public_ids = {item.test_id for item in partition.base_tests}
        public_ids.update(item.test_id for item in partition.feedback_tests)
        self.assertEqual(
            len(partition.base_tests) + len(partition.feedback_tests),
            len(public_ids),
        )
        self.assertTrue(
            all(item.test_id.startswith("phase8_validation_") for item in partition.feedback_tests)
        )


if __name__ == "__main__":
    unittest.main()
