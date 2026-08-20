"""Aggregate Phase 9 checkpoints into bounded research artifacts."""

import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from benchmark.config import (
    CODEFLAWS_REPAIR_PILOT,
    PHASE8_EVALUATION_SET,
    PHASE9_ARTIFACT_ROOT,
    PHASE9_DIFFERENTIAL_MANIFEST,
    PHASE9_PATCH_CORPUS,
    PHASE9_PROTOCOL,
    PROJECT_ROOT,
)
from benchmark.models import BenchmarkCase, load_manifest
from repair_phase8.partition import canonical_hash

from .corpus import load_patch_source


FROZEN_ORIGINAL_RESULTS = {
    "phase7": {
        "A": {"attempted": 50, "validated": 40},
        "B": {"attempted": 50, "validated": 39},
        "C": {"attempted": 50, "validated": 46},
    },
    "phase8_stage1": {"Initial": {"attempted": 100, "validated": 85}},
    "phase8_stage2": {
        "R": {"attempted": 6, "validated": 4},
        "F": {"attempted": 6, "validated": 4},
    },
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_name(patch_id: str) -> str:
    return patch_id.replace("/", "__") + ".json"


def load_phase9_records() -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]
]:
    corpus = _load(PHASE9_PATCH_CORPUS)
    differential = _load(PHASE9_DIFFERENTIAL_MANIFEST)
    references = [
        _load(PHASE9_ARTIFACT_ROOT / "reference" / f"{case_id}.json")
        for case_id in sorted({item["case_id"] for item in corpus["entries"]})
    ]
    patches = [
        _load(PHASE9_ARTIFACT_ROOT / "patch" / _checkpoint_name(item["patch_id"]))
        for item in corpus["entries"]
    ]
    return corpus, differential, references, patches


def _affected_patch_counts(patches: Iterable[dict[str, Any]]) -> Counter[str]:
    values: Counter[str] = Counter()
    for patch in patches:
        kinds = {
            item["failure_type"]
            for item in (
                patch.get("sanitizer_findings", [])
                + patch.get("differential_findings", [])
            )
        }
        values.update(kinds)
    return values


def _finding_counts(patches: Iterable[dict[str, Any]]) -> Counter[str]:
    values: Counter[str] = Counter()
    for patch in patches:
        values.update(
            item["failure_type"]
            for item in (
                patch.get("sanitizer_findings", [])
                + patch.get("differential_findings", [])
            )
        )
    return values


def _group_audits(
    entries: list[dict[str, Any]], patches_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for phase, groups in FROZEN_ORIGINAL_RESULTS.items():
        result[phase] = {}
        for group, frozen in groups.items():
            selected = [
                item
                for item in entries
                if item["phase"] == phase and item["arm_or_group"] == group
            ]
            result[phase][group] = {
                **frozen,
                "extracted_patch_count": len(selected),
                "strongly_validated": sum(
                    patches_by_id[item["patch_id"]]["strongly_validated"]
                    for item in selected
                ),
            }
    return result


def _bounded_patch_result(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "V3": value["V3"],
        "V4": value["V4"],
        "case_id": value["case_id"],
        "differential_findings": value.get("differential_findings", []),
        "execution_counts": value.get("execution_counts", {}),
        "patch_id": value["patch_id"],
        "primary_failure": value.get("primary_failure"),
        "sanitizer_findings": value.get("sanitizer_findings", []),
        "strongly_validated": value["strongly_validated"],
        "time_ms": value.get("time_ms", 0),
    }


def build_result_manifest() -> dict[str, Any]:
    corpus, differential, references, patches = load_phase9_records()
    entries = corpus["entries"]
    patches_by_id = {item["patch_id"]: item for item in patches}
    if len(patches_by_id) != len(entries):
        raise ValueError("Phase 9 patch checkpoint coverage is incomplete or duplicated")
    if {item["patch_id"] for item in entries} != set(patches_by_id):
        raise ValueError("Phase 9 patch checkpoint identities do not match corpus")
    if len(references) != corpus["case_count"]:
        raise ValueError("Phase 9 reference checkpoint coverage mismatch")

    for entry in entries:
        patch = patches_by_id[entry["patch_id"]]
        expected_strong = (
            entry["hidden_validation_pass"]
            and patch["V3"] == "PASS"
            and patch["V4"] == "PASS"
        )
        if patch["strongly_validated"] != expected_strong:
            raise ValueError(f"invalid strong label: {entry['patch_id']}")
        if not entry["hidden_validation_pass"] and (
            patch["V3"] != "N/A" or patch["V4"] != "N/A"
        ):
            raise ValueError(f"V2-ineligible patch executed: {entry['patch_id']}")

    v1 = sum(item["repair_time_pass"] for item in entries)
    v2 = sum(item["hidden_validation_pass"] for item in entries)
    traditional_rejections = sum(
        item["repair_time_pass"] and not item["hidden_validation_pass"]
        for item in entries
    )
    v3_rejections = sum(
        item["hidden_validation_pass"]
        and patches_by_id[item["patch_id"]]["V3"] == "FAIL"
        for item in entries
    )
    v4_rejections = sum(
        item["hidden_validation_pass"]
        and patches_by_id[item["patch_id"]]["V4"] == "FAIL"
        for item in entries
    )
    applicable = sum(
        item["hidden_validation_pass"]
        and (
            patches_by_id[item["patch_id"]]["V3"] != "N/A"
            or patches_by_id[item["patch_id"]]["V4"] != "N/A"
        )
        for item in entries
    )
    additional_rejections = sum(
        item["hidden_validation_pass"]
        and (
            patches_by_id[item["patch_id"]]["V3"] == "FAIL"
            or patches_by_id[item["patch_id"]]["V4"] == "FAIL"
        )
        for item in entries
    )
    reference_exclusions: Counter[str] = Counter()
    reference_executions: Counter[str] = Counter()
    for reference in references:
        reference_exclusions.update(reference["sanitizer_exclusion_counts"])
        reference_executions.update(reference["execution_counts"])
    patch_executions: Counter[str] = Counter()
    for patch in patches:
        patch_executions.update(patch.get("execution_counts", {}))

    value: dict[str, Any] = {
        "computational_cost": {
            "patch_execution_counts": dict(sorted(patch_executions.items())),
            "patch_time_ms": sum(item.get("time_ms", 0) for item in patches),
            "reference_execution_counts": dict(sorted(reference_executions.items())),
            "reference_time_ms": sum(item["time_ms"] for item in references),
            "total_program_executions": sum(reference_executions.values())
            + sum(patch_executions.values()),
            "total_time_ms": sum(item["time_ms"] for item in references)
            + sum(item.get("time_ms", 0) for item in patches),
        },
        "corpus_manifest_hash": corpus["overall_manifest_hash"],
        "differential": {
            "accepted_test_count": differential["accepted_test_count"],
            "candidate_count": differential["proposal_count"],
            "manifest_hash": differential["overall_manifest_hash"],
            "zero_accepted_case_count": differential["zero_accepted_case_count"],
        },
        "failure_modes": {
            "affected_patch_counts": dict(sorted(_affected_patch_counts(patches).items())),
            "finding_instance_counts": dict(sorted(_finding_counts(patches).items())),
            "reference_sanitizer_exclusion_counts": dict(sorted(reference_exclusions.items())),
        },
        "group_audits": _group_audits(entries, patches_by_id),
        "leakage_audit": {
            "generated_input_text_committed": False,
            "llm_calls": 0,
            "raw_reasoning_committed": False,
            "repair_feedback_from_phase9": False,
        },
        "metrics": {
            "additional_rejection_denominator": applicable,
            "additional_rejection_rate": additional_rejections / applicable,
            "additional_rejections": additional_rejections,
            "strongly_validated": sum(
                item["strongly_validated"] for item in patches
            ),
            "traditional_overfitting_rate": traditional_rejections / v1,
            "V1_plausible": v1,
            "V1_to_V2_rejections": traditional_rejections,
            "V2_existing_validated": v2,
            "V2_with_V4_NA": sum(
                item["hidden_validation_pass"]
                and patches_by_id[item["patch_id"]]["V4"] == "N/A"
                for item in entries
            ),
            "V2_to_V3_rejections": v3_rejections,
            "V2_to_V4_rejections": v4_rejections,
        },
        "patch_count": corpus["patch_count"],
        "patch_results": [_bounded_patch_result(item) for item in patches],
        "protocol_file_sha256": sha256_file(PHASE9_PROTOCOL),
        "protocol_version": "phase9-validation-results-v1",
        "reference_audit": [
            {
                "accepted_count": item["accepted_count"],
                "case_id": item["case_id"],
                "execution_counts": item["execution_counts"],
                "official_test_count": item["official_test_count"],
                "proposal_count": item["proposal_count"],
                "reference_normal_compile_success": item[
                    "reference_normal_compile_success"
                ],
                "reference_sanitizer_compile_success": item[
                    "reference_sanitizer_compile_success"
                ],
                "sanitizer_eligible_official_test_count": len(
                    item["sanitizer_eligible_official_test_ids"]
                ),
                "sanitizer_exclusion_counts": item["sanitizer_exclusion_counts"],
                "time_ms": item["time_ms"],
            }
            for item in references
        ],
        "source_artifact_hashes": corpus["source_sets"],
        "unique_case_count": corpus["case_count"],
    }
    value["overall_manifest_hash"] = canonical_hash(value)
    return value


def _cases() -> dict[str, BenchmarkCase]:
    return {
        case.case_id: case
        for path in (CODEFLAWS_REPAIR_PILOT, PHASE8_EVALUATION_SET)
        for case in load_manifest(path)
    }


def deterministic_case_studies(
    corpus: dict[str, Any], result: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    entries = {item["patch_id"]: item for item in corpus["entries"]}
    cases = _cases()
    selected: dict[str, list[dict[str, Any]]] = {"V3": [], "V4": []}
    seen: dict[str, set[str]] = {"V3": set(), "V4": set()}
    for stage in ("V3", "V4"):
        failures = sorted(
            (item for item in result["patch_results"] if item[stage] == "FAIL"),
            key=lambda item: (item["case_id"], item["patch_id"]),
        )
        for patch in failures:
            if patch["case_id"] in seen[stage]:
                continue
            entry = entries[patch["patch_id"]]
            case = cases[patch["case_id"]]
            diff = list(
                difflib.unified_diff(
                    case.get_buggy_source().splitlines(),
                    load_patch_source(entry).splitlines(),
                    lineterm="",
                )
            )
            changes = [
                line
                for line in diff
                if (line.startswith("+") or line.startswith("-"))
                and not line.startswith(("+++", "---"))
            ]
            findings = (
                patch["sanitizer_findings"]
                if stage == "V3"
                else patch["differential_findings"]
            )
            selected[stage].append(
                {
                    "case_id": patch["case_id"],
                    "changed_line_count": len(changes),
                    "changed_line_excerpt": changes[:6],
                    "failure_type": patch["primary_failure"],
                    "finding_count": len(findings),
                    "first_finding": findings[0],
                    "patch_id": patch["patch_id"],
                }
            )
            seen[stage].add(patch["case_id"])
            if len(selected[stage]) == 3:
                break
    return selected


def percent(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "N/A"
