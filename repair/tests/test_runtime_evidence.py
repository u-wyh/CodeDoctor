"""Frozen runtime evidence capture, integrity, and bulk-gate tests."""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT,
    PROJECT_ROOT,
    REPAIR_PILOT_FL,
    RUNTIME_EVIDENCE_PROMPT_AUDIT,
)
from benchmark.models import (
    BenchmarkCase,
    BenchmarkTest,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
    load_manifest,
)
from benchmark.scripts.run_repair_ablation import main as run_repair_main
from repair.context import build_repair_context, load_fl_records
from repair.models import (
    EvidenceGroup,
    PatchClassification,
    PatchEvaluation,
    TestResult,
)
from repair.prompting import render_prompt
from repair.runtime_evidence import (
    freeze_runtime_evidence,
    load_frozen_runtime_evidence,
)


def _case(case_id: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        dataset="test",
        language="C",
        problem=ProblemIdentity("1", "A"),
        buggy=ProgramArtifact("buggy.c", "buggy"),
        reference=ProgramArtifact("reference.c", "reference"),
        tests=TestSuites(
            repair_tests=(BenchmarkTest("n1", "input", "output"),),
            validation_tests=(),
        ),
        metadata={},
    )


def _evaluation(case: BenchmarkCase) -> PatchEvaluation:
    result = TestResult("n1", False, "value \n", "warning\n", 0, False)
    return PatchEvaluation(
        True,
        "compile out\n",
        "",
        0,
        (result,),
        (),
        False,
        False,
        PatchClassification.REPAIR_TEST_FAILED,
        ("repair_test_failed",),
    )


class RuntimeEvidenceTests(unittest.TestCase):
    def _freeze(self, root: Path):
        pilot = root / "pilot.jsonl"
        protocol = root / "protocol.json"
        pilot.write_text("frozen pilot\n", encoding="utf-8")
        protocol.write_text(
            json.dumps({"protocol_version": "repair-v2"}) + "\n",
            encoding="utf-8",
        )
        cases = [_case("case-a"), _case("case-b")]
        artifact_root = root / "snapshots"
        manifest = root / "manifest.json"
        frozen = freeze_runtime_evidence(
            cases,
            artifact_root=artifact_root,
            manifest_path=manifest,
            pilot_path=pilot,
            repair_protocol_path=protocol,
            project_root=root,
            capture=_evaluation,
            backend_metadata={"backend": "test", "transport_retries": 0},
            generated_at="2026-08-16T00:00:00+00:00",
        )
        return cases, pilot, protocol, manifest, frozen

    def test_capture_round_trip_preserves_exact_text_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cases, _, _, manifest, frozen = self._freeze(Path(temporary))
            self.assertEqual(2, frozen.validation["case_count"])
            loaded = load_frozen_runtime_evidence(
                cases, manifest_path=manifest, project_root=Path(temporary)
            )
            result = loaded.evaluations["case-a"].repair_tests[0]
            self.assertEqual("value \n", result.stdout)
            self.assertEqual("warning\n", result.stderr)
            self.assertEqual("n1", result.test_id)

    def test_corrupt_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases, _, _, manifest, _ = self._freeze(root)
            value = json.loads(manifest.read_text())
            snapshot = root / value["artifacts"][0]["path"]
            snapshot.write_text(snapshot.read_text() + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
                load_frozen_runtime_evidence(
                    cases, manifest_path=manifest, project_root=root
                )

    def test_manifest_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases, _, _, manifest, _ = self._freeze(root)
            value = json.loads(manifest.read_text())
            value["runner"]["backend"] = "changed"
            manifest.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
                load_frozen_runtime_evidence(
                    cases, manifest_path=manifest, project_root=root
                )

    def test_missing_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases, _, _, manifest, _ = self._freeze(root)
            value = json.loads(manifest.read_text())
            (root / value["artifacts"][0]["path"]).unlink()
            with self.assertRaisesRegex(FileNotFoundError, "snapshot missing"):
                load_frozen_runtime_evidence(
                    cases, manifest_path=manifest, project_root=root
                )

    def test_pilot_and_protocol_hash_mismatch_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases, pilot, _, manifest, _ = self._freeze(root)
            pilot.write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Repair Pilot manifest hash"):
                load_frozen_runtime_evidence(
                    cases, manifest_path=manifest, project_root=root
                )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases, _, protocol, manifest, _ = self._freeze(root)
            protocol.write_text('{"protocol_version":"changed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repair protocol hash"):
                load_frozen_runtime_evidence(
                    cases, manifest_path=manifest, project_root=root
                )

    def test_production_freeze_covers_all_50_cases(self) -> None:
        cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
        frozen = load_frozen_runtime_evidence(cases)
        self.assertEqual(50, frozen.validation["case_count"])
        self.assertEqual(
            sum(len(case.tests.repair_tests) for case in cases),
            frozen.validation["repair_test_count"],
        )

    def test_groups_render_only_registered_frozen_evidence(self) -> None:
        cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
        case = cases[0]
        required = [PROJECT_ROOT / case.buggy.source_path]
        required.extend(
            PROJECT_ROOT / str(path)
            for test in case.tests.repair_tests
            for path in (test.input_path, test.expected_output_path)
        )
        if not all(path.is_file() for path in required):
            self.skipTest("requires external artifact package")
        frozen = load_frozen_runtime_evidence(cases)
        fl = load_fl_records(REPAIR_PILOT_FL)[case.case_id]
        prompts = {
            group.value: render_prompt(
                build_repair_context(
                    case, group, fl, frozen.evaluations[case.case_id]
                ),
                group,
            )
            for group in EvidenceGroup
        }
        self.assertNotIn("## Repair-test execution evidence", prompts["A"].user)
        self.assertNotIn("## Repair-test execution evidence", prompts["B"].user)
        self.assertIn("## Repair-test execution evidence", prompts["C"].user)

    def test_production_prompt_reproducibility_audit_passes(self) -> None:
        value = json.loads(RUNTIME_EVIDENCE_PROMPT_AUDIT.read_text())
        self.assertEqual(150, value["prompts_checked"])
        self.assertTrue(value["all_prompt_hashes_identical_across_reloads"])
        self.assertTrue(value["target_case_c_ten_render_hashes_identical"])
        self.assertEqual("passed", value["leakage_audit"]["status"])

    def test_bulk_gate_refuses_invalid_freeze_before_generation(self) -> None:
        argv = [
            "run_repair_ablation.py",
            "--provider",
            "deepseek",
            "--cases",
            "259-B-bug-13083263-13083279",
            "--confirm-bulk",
        ]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "offline-test-key"}), patch(
            "sys.argv", argv
        ), patch(
            "benchmark.scripts.run_repair_ablation.load_frozen_runtime_evidence",
            side_effect=ValueError("corrupt snapshot"),
        ), patch("sys.stderr", new_callable=io.StringIO) as stderr, self.assertRaises(
            SystemExit
        ) as raised:
            run_repair_main()
        self.assertEqual(2, raised.exception.code)
        self.assertIn("frozen runtime evidence gate failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
