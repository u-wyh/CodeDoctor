"""Formal corpus identity and duplicate checks."""

import unittest

from validation_phase9.corpus import build_formal_patch_corpus, finalize_corpus


def entry(patch_id: str, artifact: str, source_hash: str = "source") -> dict[str, object]:
    return {
        "case_id": "case",
        "patch_id": patch_id,
        "patch_source_hash": source_hash,
        "phase": "phase7",
        "source_artifact_path": artifact,
        "valid_output": True,
    }


class CorpusTests(unittest.TestCase):
    def test_actual_corpus_contains_only_frozen_formal_artifacts(self) -> None:
        value = build_formal_patch_corpus()
        self.assertEqual((245, 141), (value["patch_count"], value["case_count"]))
        self.assertEqual(150, value["source_sets"]["attempted"]["phase7"])
        for item in value["entries"]:
            path = item["source_artifact_path"]
            self.assertNotIn("smoke", path.lower())
            self.assertNotIn("fake", path.lower())

    def test_hash_is_stable_and_duplicate_source_content_is_allowed(self) -> None:
        first = entry("p/A", "a.json")
        second = entry("p/B", "b.json")
        left = finalize_corpus([first, second], {"formal_only": True})
        right = finalize_corpus([second, first], {"formal_only": True})
        self.assertEqual(left["overall_manifest_hash"], right["overall_manifest_hash"])
        self.assertEqual(1, left["duplicate_patch_source_hashes"])

    def test_duplicate_patch_or_artifact_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "patch_id"):
            finalize_corpus([entry("p", "a"), entry("p", "b")], {})
        with self.assertRaisesRegex(ValueError, "artifact"):
            finalize_corpus([entry("p", "a"), entry("q", "a")], {})

    def test_invalid_output_is_not_a_patch(self) -> None:
        value = entry("p", "a")
        value["valid_output"] = False
        with self.assertRaisesRegex(ValueError, "extracted patches"):
            finalize_corpus([value], {})


if __name__ == "__main__":
    unittest.main()
