"""Verify the frozen Phase 9 result manifest and report without writing them."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE9_PATCH_CORPUS,
    PHASE9_REPORT,
    PHASE9_RESULT_MANIFEST,
)
from benchmark.frozen_artifacts import FrozenArtifactError  # noqa: E402
from validation_phase9.reporting import (  # noqa: E402
    build_result_manifest,
    deterministic_case_studies,
    percent,
)

def _audit_table(result: dict[str, object], phase: str) -> list[str]:
    rows = []
    for group, item in result["group_audits"][phase].items():
        rows.append(
            f"| {group} | {item['validated']}/{item['attempted']} "
            f"({percent(item['validated'], item['attempted'])}) | "
            f"{item['strongly_validated']}/{item['attempted']} "
            f"({percent(item['strongly_validated'], item['attempted'])}) | "
            f"{item['extracted_patch_count']} |"
        )
    return rows


def _case_study_lines(studies: dict[str, list[dict[str, object]]]) -> list[str]:
    lines = ["### V3 sanitizer cases", ""]
    if not studies["V3"]:
        lines.append("No V2-passing patch failed V3; no V3 case was selected.")
    for item in studies["V3"]:
        lines.extend(_one_case(item, "sanitizer"))
    lines.extend(["", "### V4 differential cases", ""])
    for item in studies["V4"]:
        lines.extend(_one_case(item, "differential"))
    return lines


def _one_case(item: dict[str, object], kind: str) -> list[str]:
    finding = item["first_finding"]
    excerpt = "\n".join(item["changed_line_excerpt"]) or "(no line-level diff excerpt)"
    exposure = (
        f"`{finding['failure_type']}` on `{finding['test_id']}`; "
        f"actual output hash `{finding.get('actual_output_hash', 'N/A')}`"
    )
    if "expected_output_hash" in finding:
        exposure += f", reference output hash `{finding['expected_output_hash']}`"
    return [
        f"#### `{item['case_id']}`",
        "",
        f"- Patch: `{item['patch_id']}`.",
        "- Buggy behavior: the frozen Codeflaws buggy revision failed its benchmark "
        "tests; Phase 9 does not infer a broader formal specification.",
        f"- Patch change: {item['changed_line_count']} changed diff lines; bounded excerpt:",
        "",
        "```diff",
        excerpt,
        "```",
        "",
        "- Why existing hidden tests missed it: this patch passed every frozen V2 test, "
        f"while the failing {kind} observation lies outside that finite partition.",
        f"- Stronger evidence: {exposure} ({item['finding_count']} finding(s) total).",
        "",
    ]


def render_report(result: dict[str, object], corpus: dict[str, object]) -> str:
    metrics = result["metrics"]
    diff = result["differential"]
    failures = result["failure_modes"]
    affected = failures["affected_patch_counts"]
    instances = failures["finding_instance_counts"]
    exclusions = failures["reference_sanitizer_exclusion_counts"]
    cost = result["computational_cost"]
    studies = deterministic_case_studies(corpus, result)
    lines = [
        "# Phase 9: Patch Validation Strength and Overfitting",
        "",
        "## 1. Research Questions",
        "",
        "- **RQ1:** How many V1 plausible patches are rejected by existing hidden validation?",
        "- **RQ2:** How many V2 validated patches exhibit sanitizer-detectable failures?",
        "- **RQ3:** How many V2 validated patches diverge on reference-accepted differential stress inputs?",
        "- **RQ4:** How do the frozen Phase 7/8 rates change under stronger validation?",
        "",
        "Phase 9 made **0 LLM calls** and did not repair any rejected patch.",
        "",
        "## 2. Formal Patch Corpus",
        "",
        f"The corpus contains {result['patch_count']} extracted patches from "
        f"{result['unique_case_count']} unique cases. The corpus manifest hash is "
        f"`{result['corpus_manifest_hash']}`. Invalid or missing model outputs remain "
        "in the frozen upstream denominators but are not treated as executable patches.",
        "",
        "## 3. Validation Ladder",
        "",
        "`V0 compile -> V1 repair-time validation -> V2 existing hidden validation -> "
        "V3 ASan+UBSan -> V4 reference-based differential validation`.",
        "",
        "A **Strongly Validated Patch** is exactly `V2 PASS AND V3 PASS AND V4 PASS`. "
        "`V4=N/A` is never strong.",
        "",
        "## 4. Existing Plausible / Validated Definitions",
        "",
        "V1 uses each frozen experiment's repair-time test result. V2 uses the existing "
        "evaluation-only hidden partition. Neither definition is changed post hoc.",
        "",
        "## 5. Sanitizer Protocol",
        "",
        "V3 compiles C99 sources with ASan+UBSan, frame pointers, and non-PIE settings. "
        "Only official tests on which the reference is sanitizer-clean are eligible. "
        "Every run retains the 5 s timeout and Docker's 1 CPU, 256 MB, and 64 PID bounds.",
        "",
        "## 6. Differential Test Generation",
        "",
        "Deterministic Numeric Mutation v1 uses seed `20260820`, signed whitespace-delimited "
        "integers, values `{0, 1, -1, x-1, x+1}`, SHA-256 ordering, a 500 proposal cap, "
        "and a 100 acceptance cap per case.",
        "",
        f"It proposed {diff['candidate_count']:,} candidates and froze "
        f"{diff['accepted_test_count']:,} reference-accepted differential stress inputs. "
        f"{diff['zero_accepted_case_count']} cases have no accepted differential input.",
        "",
        "## 7. Reference Acceptance Filter",
        "",
        "An input is accepted only when two normal reference runs both exit zero, do not "
        "time out, produce identical stdout, and the sanitizer reference run is clean. "
        "These are reference-accepted stress inputs, not asserted formally valid inputs.",
        "",
        f"Reference official-test exclusions: ASan={exclusions.get('ASan', 0)}, "
        f"UBSan={exclusions.get('UBSan', 0)}, timeout={exclusions.get('sanitizer_timeout', 0)}.",
        "",
        "## 8. Reproducibility",
        "",
        f"- Protocol file SHA-256: `{result['protocol_file_sha256']}`",
        f"- Patch corpus manifest: `{result['corpus_manifest_hash']}`",
        f"- Differential manifest: `{diff['manifest_hash']}`",
        f"- Result manifest: `{result['overall_manifest_hash']}`",
        "",
        "The same case shares one frozen differential set across all arms. Generated input "
        "text remains in ignored local checkpoints and is absent from committed manifests.",
        "",
        "## 9. Main Results",
        "",
        "| Transition | Count | Rate |",
        "|---|---:|---:|",
        f"| V1 plausible | {metrics['V1_plausible']} | "
        f"{percent(metrics['V1_plausible'], result['patch_count'])} of extracted patches |",
        f"| V1 -> V2 rejected | {metrics['V1_to_V2_rejections']} | "
        f"{percent(metrics['V1_to_V2_rejections'], metrics['V1_plausible'])} of V1 |",
        f"| V2 existing validated | {metrics['V2_existing_validated']} | "
        f"{percent(metrics['V2_existing_validated'], result['patch_count'])} of extracted patches |",
        f"| V2 -> V3 rejected | {metrics['V2_to_V3_rejections']} | "
        f"{percent(metrics['V2_to_V3_rejections'], metrics['V2_existing_validated'])} of V2 |",
        f"| V2 -> V4 rejected | {metrics['V2_to_V4_rejections']} | "
        f"{percent(metrics['V2_to_V4_rejections'], metrics['V2_existing_validated'] - metrics['V2_with_V4_NA'])} of V4-applicable V2 |",
        f"| Strongly validated | {metrics['strongly_validated']} | "
        f"{percent(metrics['strongly_validated'], result['patch_count'])} of extracted patches |",
        "",
        "## 10. Additional Rejection Rate",
        "",
        f"The pre-registered rate is **{metrics['additional_rejections']}/"
        f"{metrics['additional_rejection_denominator']} = "
        f"{percent(metrics['additional_rejections'], metrics['additional_rejection_denominator'])}**. "
        "The denominator contains V2 patches with at least one applicable stronger validation. "
        f"Separately, {metrics['V2_with_V4_NA']} V2 patches have insufficient differential evidence.",
        "",
        "## 11. Phase 7 Strong Validation Audit",
        "",
        "The original Phase 7 values remain frozen; strong results are a post-hoc audit.",
        "",
        "| Arm | Original V2 | Strong | Extracted patches |",
        "|---|---:|---:|---:|",
        *_audit_table(result, "phase7"),
        "",
        "## 12. Phase 8 Strong Validation Audit",
        "",
        "| Arm | Original V2 | Strong | Extracted patches |",
        "|---|---:|---:|---:|",
        *_audit_table(result, "phase8_stage1"),
        *_audit_table(result, "phase8_stage2"),
        "",
        "The Stage 2 denominator remains six per arm; one F response had no executable patch.",
        "",
        "## 13. Failure Modes",
        "",
        f"Affected patches: ASan={affected.get('ASan', 0)}, UBSan={affected.get('UBSan', 0)}, "
        f"differential mismatch={affected.get('differential_output_mismatch', 0)}, "
        f"runtime error={affected.get('differential_runtime_error', 0)}, "
        f"timeout={affected.get('differential_timeout', 0)}.",
        "",
        f"Finding instances: mismatch={instances.get('differential_output_mismatch', 0):,}, "
        f"runtime error={instances.get('differential_runtime_error', 0):,}, "
        f"timeout={instances.get('differential_timeout', 0):,}. A patch may contribute "
        "multiple findings but has one deterministic primary failure.",
        "",
        "## 14. Case Studies",
        "",
        *_case_study_lines(studies),
        "",
        "## 15. Computational Cost",
        "",
        f"Phase 9 recorded {cost['total_program_executions']:,} program executions: "
        f"reference normal={cost['reference_execution_counts'].get('reference_normal', 0):,}, "
        f"reference sanitizer={cost['reference_execution_counts'].get('reference_sanitizer', 0):,}, "
        f"patch sanitizer={cost['patch_execution_counts'].get('sanitizer', 0):,}, and "
        f"patch differential={cost['patch_execution_counts'].get('differential', 0):,}. "
        f"Summed batch wall time was {cost['total_time_ms'] / 1000:.1f} s "
        f"({cost['total_time_ms'] / 60000:.1f} min), excluding Python aggregation and regression tests.",
        "",
        "## 16. Threats to Validity",
        "",
        "- Reference-accepted input does not imply a formally valid problem input.",
        "- Numeric mutation has limited input-space and semantic coverage.",
        "- Differential tests are finite and cannot establish equivalence.",
        "- Sanitizer coverage is incomplete and depends on executed paths.",
        "- Codeflaws may not represent other defects, programs, or repair systems.",
        "- Multiple patches from the same case are statistically dependent.",
        "- V4=N/A conservatively prevents a strong label but does not prove failure.",
        "- Strong validation provides additional empirical evidence, not formal correctness.",
        "",
        "## 17. Conclusion",
        "",
        f"RQ1: hidden validation rejected {metrics['V1_to_V2_rejections']}/"
        f"{metrics['V1_plausible']} plausible patches. RQ2: V3 rejected "
        f"{metrics['V2_to_V3_rejections']} V2 patches. RQ3: V4 rejected "
        f"{metrics['V2_to_V4_rejections']} of "
        f"{metrics['V2_existing_validated'] - metrics['V2_with_V4_NA']} V4-applicable V2 patches. "
        f"RQ4: only {metrics['strongly_validated']} extracted patches survived the full ladder, "
        "and every frozen Phase 7/8 arm has a lower strong rate than its original V2 rate. "
        "Validated Patch and Strongly Validated Patch both remain empirical labels, not formal correctness.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    result = build_result_manifest()
    corpus = json.loads(PHASE9_PATCH_CORPUS.read_text(encoding="utf-8"))
    if not PHASE9_RESULT_MANIFEST.is_file() or not PHASE9_REPORT.is_file():
        raise FrozenArtifactError(
            "Required frozen artifact missing. Reproduction requires external "
            "artifact package. Frozen outputs were not modified."
        )
    frozen_result = json.loads(PHASE9_RESULT_MANIFEST.read_text(encoding="utf-8"))
    if result != frozen_result:
        raise FrozenArtifactError(
            "Frozen artifact hash mismatch: computed Phase 9 result does not match "
            "the tracked manifest. Frozen outputs were not modified."
        )
    if render_report(result, corpus) != PHASE9_REPORT.read_text(encoding="utf-8"):
        raise FrozenArtifactError(
            "Frozen artifact hash mismatch: computed Phase 9 report does not match "
            "the tracked report. Frozen outputs were not modified."
        )
    print(
        f"Phase 9 report verified: strong={result['metrics']['strongly_validated']} "
        f"result_hash={result['overall_manifest_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
