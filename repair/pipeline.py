"""One-attempt repair pipeline with exact resume keys and post-generation validation."""

import difflib
import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from benchmark.models import BenchmarkCase

from .artifacts import ArtifactStore, cache_key
from .context import build_repair_context
from .evaluator import evaluate_source
from .extraction import extract_source
from .models import (
    EvidenceGroup,
    PatchClassification,
    PatchEvaluation,
)
from .prompting import render_prompt
from .provider import ModelError, RepairModel


def _persist(
    store: ArtifactStore,
    case_id: str,
    group: EvidenceGroup,
    key: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    store.write(case_id, group, key, record)
    persisted = store.load(case_id, group, key)
    if persisted is None:
        raise OSError("repair artifact was not persisted")
    return persisted


def changed_buggy_lines(before: str, after: str) -> tuple[int, ...]:
    original = before.splitlines()
    patched = after.splitlines()
    changed: set[int] = set()
    matcher = difflib.SequenceMatcher(a=original, b=patched, autojunk=False)
    for tag, old_start, old_end, _, _ in matcher.get_opcodes():
        if tag == "equal":
            continue
        if old_start == old_end:
            changed.add(max(1, old_start))
        else:
            changed.update(range(old_start + 1, old_end + 1))
    return tuple(sorted(changed))


def _failure_modes(
    evaluation: PatchEvaluation, baseline: PatchEvaluation
) -> list[str]:
    modes = list(evaluation.failure_modes)
    if evaluation.classification is PatchClassification.REPAIR_TEST_FAILED:
        original = {item.test_id: item.passed for item in baseline.repair_tests}
        failed = [item for item in evaluation.repair_tests if not item.passed]
        if any(not original.get(item.test_id, False) for item in failed):
            modes.append("still_fails_original_failing_tests")
        if any(original.get(item.test_id, False) for item in failed):
            modes.append("regression_on_previously_passing_repair_tests")
    return sorted(set(modes))


def run_repair_attempt(
    case: BenchmarkCase,
    group: EvidenceGroup,
    model: RepairModel,
    fl_record: dict[str, Any] | None,
    baseline: PatchEvaluation,
    store: ArtifactStore,
    *,
    resume: bool,
    evaluator: Callable[[BenchmarkCase, str], PatchEvaluation] = evaluate_source,
    experimental: bool = True,
) -> dict[str, Any]:
    context = build_repair_context(case, group, fl_record, baseline)
    prompt = render_prompt(context, group)
    key = cache_key(case.case_id, group, prompt, model.parameters)
    if resume:
        cached = store.load(case.case_id, group, key)
        if cached is not None and cached.get("completed") is True:
            return cached

    record: dict[str, Any] = {
        "attempt": 1,
        "cache_key": key,
        "case_id": case.case_id,
        "completed": False,
        "experimental": experimental,
        "group": group.value,
        "model_parameters": model.parameters.cache_view(),
        "prompt": {
            "hash": prompt.prompt_hash,
            "system": prompt.system,
            "template_version": prompt.template_version,
            "user": prompt.user,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = model.generate(prompt)
    except ModelError as exc:
        record.update(
            {
                "classification": PatchClassification.MODEL_ERROR.value,
                "error": f"{type(exc).__name__}: {exc}",
                "completed": True,
            }
        )
        return _persist(store, case.case_id, group, key, record)

    extraction = extract_source(response.text)
    record["model_response"] = {
        "finish_reason": response.finish_reason,
        "id": response.response_id,
        "raw": response.text,
        "response_hash": hashlib.sha256(response.text.encode()).hexdigest(),
    }
    record["extraction"] = asdict(extraction)
    if extraction.source is None:
        record.update(
            {
                "classification": PatchClassification.INVALID_MODEL_OUTPUT.value,
                "completed": True,
            }
        )
        return _persist(store, case.case_id, group, key, record)

    evaluation = evaluator(case, extraction.source)
    changed = changed_buggy_lines(context.buggy_source, extraction.source)
    fl_lines = {item.line for item in context.suspicious_locations}
    record.update(
        {
            "classification": evaluation.classification.value,
            "completed": True,
            "evaluation": evaluation.to_dict(),
            "failure_modes": _failure_modes(evaluation, baseline),
            "patch_analysis": {
                "changed_buggy_line_count": len(changed),
                "changed_buggy_lines": list(changed),
                "modified_fl_top_k": bool(set(changed) & fl_lines),
            },
        }
    )
    return _persist(store, case.case_id, group, key, record)
