"""Tests for evaluation-only buggy-side diff mapping."""

import unittest

from fault_localization.ground_truth import derive_fault_lines


class GroundTruthTests(unittest.TestCase):
    def test_single_line_modification(self) -> None:
        self.assertEqual(
            (2,), derive_fault_lines("a\nbug\nc\n", "a\nfix\nc\n")
        )

    def test_multi_line_modification(self) -> None:
        self.assertEqual(
            (2, 3),
            derive_fault_lines("a\nbug1\nbug2\nd\n", "a\nfix\nd\n"),
        )

    def test_buggy_side_deletion(self) -> None:
        self.assertEqual(
            (2,), derive_fault_lines("a\nextra\nc\n", "a\nc\n")
        )

    def test_blank_only_deletion_maps_to_nonblank_context(self) -> None:
        self.assertEqual(
            (1,), derive_fault_lines("code\n\nnext\n", "code\nnext\n")
        )

    def test_reference_only_insertion_maps_to_previous_context(self) -> None:
        self.assertEqual(
            (1,), derive_fault_lines("a\nc\n", "a\ninserted\nc\n")
        )
        self.assertEqual(
            (1,), derive_fault_lines("a\nc\n", "inserted\na\nc\n")
        )

    def test_insertion_skips_blank_context(self) -> None:
        self.assertEqual(
            (1,),
            derive_fault_lines("code\n\nnext\n", "code\n\ninserted\nnext\n"),
        )


if __name__ == "__main__":
    unittest.main()
