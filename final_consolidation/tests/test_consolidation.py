import json
import unittest

from benchmark.config import (
    FINAL_AUDIT_SUMMARY,
    FINAL_DATASET_OVERLAP,
    FINAL_EXPERIMENT_REGISTRY,
    FINAL_FREEZE,
    FINAL_REPRODUCIBILITY_REGISTRY,
    FINAL_RESEARCH_SUMMARY,
)
from final_consolidation.consolidate import (
    build_cost_rows,
    build_dataset_audit,
    build_experiment_registry,
    build_table_rows,
    load_frozen_sources,
    validate_frozen_metrics,
)
from repair_phase8.partition import canonical_hash


class FinalConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = load_frozen_sources()
        cls.datasets = build_dataset_audit()
        cls.tables = build_table_rows(cls.values, cls.datasets)

    def test_frozen_metrics_cross_check_without_discrepancy(self):
        validate_frozen_metrics(self.values)

    def test_dataset_manifests_are_disjoint(self):
        self.assertEqual(4, len(self.datasets["datasets"]))
        for row in self.datasets["matrix"]:
            for dataset, overlap in row.items():
                if dataset != "dataset" and dataset != row["dataset"]:
                    self.assertEqual(0, overlap)

    def test_registry_contains_only_seven_formal_experiments(self):
        registry = build_experiment_registry(self.values, self.datasets)
        self.assertEqual(7, len(registry["entries"]))
        self.assertTrue(all(item["status"].startswith("formal_frozen") for item in registry["entries"]))
        names = " ".join(item["experiment_name"].lower() for item in registry["entries"])
        self.assertNotIn("smoke", names)
        self.assertNotIn("pre-experiment", names)

    def test_final_tables_preserve_core_results(self):
        fl = self.tables["table_fl_main"][-1]
        self.assertAlmostEqual(0.3475, fl["mrr"], places=4)
        self.assertAlmostEqual(0.0702, fl["deterministic_mrr_delta"], places=4)
        repair = {row["arm"]: row for row in self.tables["table_repair_main"]}
        self.assertEqual((40, 39, 46), tuple(repair[arm]["validated"] for arm in "ABC"))
        self.assertEqual("C-A", repair["C"]["secondary_paired_comparison"])
        feedback = {(row["scope"], row["arm"]): row for row in self.tables["table_feedback_main"]}
        self.assertEqual((4, 4), (feedback[("Stage 2", "R")]["validated"], feedback[("Stage 2", "F")]["validated"]))

    def test_cost_total_excludes_smoke_runs(self):
        total = build_cost_rows(self.values)[-1]
        self.assertEqual((262, 260), (total["attempted_calls"], total["successful_responses"]))
        self.assertEqual(2_596_824, total["total_tokens"])
        self.assertAlmostEqual(0.54485862, total["estimated_cost_usd"], places=8)

    def test_generated_manifests_are_self_hashed_and_frozen(self):
        for path in (
            FINAL_DATASET_OVERLAP,
            FINAL_EXPERIMENT_REGISTRY,
            FINAL_REPRODUCIBILITY_REGISTRY,
            FINAL_AUDIT_SUMMARY,
            FINAL_FREEZE,
        ):
            value = json.loads(path.read_text(encoding="utf-8"))
            claimed = value.pop("overall_manifest_hash")
            self.assertEqual(claimed, canonical_hash(value), path)
        freeze = json.loads(FINAL_FREEZE.read_text(encoding="utf-8"))
        self.assertEqual("frozen", freeze["status"])
        self.assertEqual(0, freeze["real_llm_calls"])

    def test_final_summary_preserves_claim_boundaries(self):
        summary = FINAL_RESEARCH_SUMMARY.read_text(encoding="utf-8")
        self.assertIn("Not every case improves", summary)
        self.assertIn("Strongly Validated Patch is not Formally Correct Patch", summary)
        self.assertNotIn("universally superior", summary.lower())


if __name__ == "__main__":
    unittest.main()
