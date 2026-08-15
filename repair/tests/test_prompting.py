"""Prompt-group and evaluation-boundary regression tests."""

import unittest

from repair.models import (
    EvaluationContext,
    EvidenceGroup,
    RepairContext,
    RepairTestEvidence,
    SuspiciousLocation,
    TaskExample,
)
from repair.prompting import render_prompt


SOURCE = "#include <stdio.h>\nint main(){return 0;}\n"
LOCATION = SuspiciousLocation(1, 2, "int main(){return 0;}", 1.0, 0.5, 1, 1)
EXAMPLE = TaskExample("n1", "1\n", "2\n")
EVIDENCE = RepairTestEvidence("n1", "FAIL", "3\n", "", 0, False)


class PromptingTests(unittest.TestCase):
    def test_groups_only_add_their_registered_evidence(self) -> None:
        a = render_prompt(
            RepairContext("case", "c", SOURCE, (EXAMPLE,)),
            EvidenceGroup.SOURCE_ONLY,
        )
        b = render_prompt(
            RepairContext(
                "case", "c", SOURCE, (EXAMPLE,), "available", (LOCATION,)
            ),
            EvidenceGroup.SOURCE_FL,
        )
        c = render_prompt(
            RepairContext(
                "case",
                "c",
                SOURCE,
                (EXAMPLE,),
                "available",
                (LOCATION,),
                (EVIDENCE,),
            ),
            EvidenceGroup.SOURCE_FL_EXECUTION,
        )
        self.assertNotIn("FL-v1", a.user)
        self.assertNotIn("execution evidence", a.user)
        self.assertIn("FL-v1", b.user)
        self.assertNotIn("execution evidence", b.user)
        self.assertIn("FL-v1", c.user)
        self.assertIn("execution evidence", c.user)
        self.assertIn("Common repair-time oracle", a.user)
        self.assertIn("Expected output", a.user)
        self.assertEqual(
            a.user.count("Expected output"), b.user.count("Expected output")
        )
        self.assertEqual(
            b.user.count("Expected output"), c.user.count("Expected output")
        )
        self.assertTrue(b.user.startswith(a.user))
        self.assertTrue(c.user.startswith(b.user))
        self.assertEqual(a.system, b.system)
        self.assertEqual(b.system, c.system)

    def test_evaluation_canaries_cannot_enter_prompt_type(self) -> None:
        evaluation = EvaluationContext(
            "case",
            ("VALIDATION_SECRET_TOKEN",),
            "REFERENCE_SECRET_TOKEN",
            (7,),
        )
        prompt = render_prompt(
            RepairContext(
                "case", "c", SOURCE, (EXAMPLE,), "available", (LOCATION,)
            ),
            EvidenceGroup.SOURCE_FL,
        )
        serialized = prompt.system + prompt.user
        self.assertNotIn(evaluation.reference_source_path, serialized)
        self.assertNotIn(evaluation.validation_test_ids[0], serialized)
        self.assertNotIn("ground_truth", serialized.lower())
        self.assertNotIn("reference", serialized.lower())

    def test_group_validation_rejects_mixed_contexts(self) -> None:
        with self.assertRaises(ValueError):
            render_prompt(
                RepairContext(
                    "case", "c", SOURCE, (EXAMPLE,), "available", (LOCATION,)
                ),
                EvidenceGroup.SOURCE_ONLY,
            )
        with self.assertRaises(ValueError):
            render_prompt(
                RepairContext("case", "c", SOURCE, (EXAMPLE,)),
                EvidenceGroup.SOURCE_FL,
            )

    def test_no_reliable_fl_uses_uniform_message(self) -> None:
        prompt = render_prompt(
            RepairContext(
                "case",
                "c",
                SOURCE,
                (EXAMPLE,),
                "No reliable suspicious location is available from FL-v1.",
            ),
            EvidenceGroup.SOURCE_FL,
        )
        self.assertIn(
            "No reliable suspicious location is available from FL-v1.",
            prompt.user,
        )


if __name__ == "__main__":
    unittest.main()
