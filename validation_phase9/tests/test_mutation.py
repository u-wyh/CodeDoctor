"""Deterministic Numeric Mutation v1 tests."""

import unittest

from validation_phase9.mutation import generate_numeric_mutations


class MutationTests(unittest.TestCase):
    def test_deterministic_stable_order_and_whitespace(self) -> None:
        inputs = [("t", "10  x\n-2\n")]
        first = generate_numeric_mutations(case_id="c", seed=20260820, seed_inputs=inputs)
        second = generate_numeric_mutations(case_id="c", seed=20260820, seed_inputs=inputs)
        self.assertEqual(first, second)
        self.assertTrue(all("  x\n" in item.input_text for item in first))
        self.assertEqual(sorted(item.order_hash for item in first), [item.order_hash for item in first])

    def test_caps_deduplicates_and_skips_non_tokens(self) -> None:
        value = generate_numeric_mutations(
            case_id="c",
            seed=1,
            seed_inputs=[("a", "2 2 2"), ("b", "2 2 2")],
            proposal_cap=3,
        )
        self.assertEqual(3, len(value))
        self.assertEqual(3, len({item.input_hash for item in value}))
        self.assertEqual([], generate_numeric_mutations(case_id="c", seed=1, seed_inputs=[("x", "a1 2b")]))

    def test_int64_boundaries_do_not_serialize_out_of_range(self) -> None:
        inputs = [("t", f"{-2**63} {2**63 - 1}")]
        value = generate_numeric_mutations(case_id="c", seed=1, seed_inputs=inputs)
        self.assertTrue(all(-2**63 <= item.mutation_value <= 2**63 - 1 for item in value))


if __name__ == "__main__":
    unittest.main()
