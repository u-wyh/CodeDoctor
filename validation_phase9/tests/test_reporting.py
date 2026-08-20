import json
import unittest

from benchmark.config import (
    PHASE9_DIFFERENTIAL_MANIFEST,
    PHASE9_PATCH_CORPUS,
    PHASE9_RESULT_MANIFEST,
)
from repair_phase8.partition import canonical_hash
from validation_phase9.reporting import (
    build_result_manifest,
    deterministic_case_studies,
    phase9_checkpoints_available,
)


class ReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not phase9_checkpoints_available():
            raise unittest.SkipTest("requires external artifact package")
        cls.corpus = json.loads(PHASE9_PATCH_CORPUS.read_text(encoding="utf-8"))
        cls.differential = json.loads(
            PHASE9_DIFFERENTIAL_MANIFEST.read_text(encoding="utf-8")
        )
        cls.result = build_result_manifest()

    def test_frozen_counts_and_transition_invariants(self):
        metrics = self.result["metrics"]
        self.assertEqual((245, 141), (self.result["patch_count"], self.result["unique_case_count"]))
        self.assertEqual(229, metrics["V1_plausible"])
        self.assertEqual(218, metrics["V2_existing_validated"])
        self.assertEqual(11, metrics["V1_to_V2_rejections"])
        self.assertEqual(0, metrics["V2_to_V3_rejections"])
        self.assertEqual(52, metrics["V2_to_V4_rejections"])
        self.assertEqual(149, metrics["strongly_validated"])
        self.assertEqual(52, metrics["additional_rejections"])
        self.assertEqual(217, metrics["additional_rejection_denominator"])

    def test_manifests_are_self_hashed_and_cover_same_cases(self):
        for value in (self.corpus, self.differential, self.result):
            unsigned = {key: item for key, item in value.items() if key != "overall_manifest_hash"}
            self.assertEqual(value["overall_manifest_hash"], canonical_hash(unsigned))
        self.assertEqual(
            {item["case_id"] for item in self.corpus["entries"]},
            {item["case_id"] for item in self.differential["cases"]},
        )
        self.assertEqual(
            {item["patch_id"] for item in self.corpus["entries"]},
            {item["patch_id"] for item in self.result["patch_results"]},
        )

    def test_committed_manifests_do_not_contain_generated_input_or_reasoning(self):
        for path in (
            PHASE9_DIFFERENTIAL_MANIFEST,
            PHASE9_RESULT_MANIFEST,
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('"input_text"', text)
            self.assertNotIn('"raw_reasoning":', text)
            self.assertNotIn("DEEPSEEK_API_KEY", text)

    def test_case_study_selection_is_deterministic(self):
        first = deterministic_case_studies(self.corpus, self.result)
        second = deterministic_case_studies(self.corpus, self.result)
        self.assertEqual(first, second)
        self.assertEqual([], first["V3"])
        self.assertEqual(
            [
                "110-C-bug-11176379-11176427",
                "141-B-bug-9726688-9726780",
                "143-A-bug-11615524-11615545",
            ],
            [item["case_id"] for item in first["V4"]],
        )


if __name__ == "__main__":
    unittest.main()
