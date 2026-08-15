"""Patch classification tests independent of Docker."""

import unittest

from repair.evaluator import classify_patch_results
from repair.models import PatchClassification, TestResult


def result(test_id: str, passed: bool) -> TestResult:
    return TestResult(test_id, passed, "", "", 0, False)


class EvaluatorTests(unittest.TestCase):
    def test_compile_error(self) -> None:
        values = classify_patch_results(False, (), ())
        self.assertEqual(PatchClassification.COMPILE_ERROR, values[2])

    def test_repair_failure(self) -> None:
        values = classify_patch_results(True, (result("r", False),), ())
        self.assertEqual(PatchClassification.REPAIR_TEST_FAILED, values[2])

    def test_plausible_patch_and_validation_overfitting(self) -> None:
        values = classify_patch_results(
            True, (result("r", True),), (result("v", False),)
        )
        self.assertTrue(values[0])
        self.assertFalse(values[1])
        self.assertEqual(PatchClassification.PLAUSIBLE_PATCH, values[2])
        self.assertIn("validation_overfitting", values[3])

    def test_validated_patch(self) -> None:
        values = classify_patch_results(
            True, (result("r", True),), (result("v", True),)
        )
        self.assertTrue(values[1])
        self.assertEqual(PatchClassification.VALIDATED_PATCH, values[2])


if __name__ == "__main__":
    unittest.main()
