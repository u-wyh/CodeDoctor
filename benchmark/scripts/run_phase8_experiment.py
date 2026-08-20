"""Run one explicitly approved Phase 8 stage; never chains Stage 1 into Stage 2."""

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    DEEPSEEK_EXPERIMENT_CONFIG,
    PHASE8_ARTIFACT_ROOT,
    PHASE8_ELIGIBLE_COHORT,
    PHASE8_RANDOM_SEED,
    PHASE8_STAGE1_MANIFEST,
)
from repair.deepseek import (  # noqa: E402
    DeepSeekProvider,
    model_parameters,
    resolve_api_key,
    validate_configuration,
)
from repair.evaluator import evaluate_source  # noqa: E402
from repair.models import ModelParameters  # noqa: E402
from repair.provider import FakeEchoRepairModel  # noqa: E402
from repair_phase8.artifacts import Phase8ArtifactStore  # noqa: E402
from repair_phase8.context import build_initial_context  # noqa: E402
from repair_phase8.models import Phase8Arm  # noqa: E402
from repair_phase8.partition import second_round_order  # noqa: E402
from repair_phase8.pipeline import (  # noqa: E402
    attach_provider_metadata,
    run_initial_attempt,
    run_second_attempt,
)
from repair_phase8.prompting import render_initial_prompt  # noqa: E402
from repair_phase8.protocol import (  # noqa: E402
    build_stage1_manifests,
    validate_phase8_preflight,
    validate_stage2_gate,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _model(provider: str, timeout: float):
    if provider == "deepseek":
        validate_configuration(DEEPSEEK_EXPERIMENT_CONFIG)
        api_key, environment = resolve_api_key(os.environ)
        if not api_key or not environment:
            raise ValueError("DeepSeek API credential unavailable")
        return DeepSeekProvider(model_parameters(timeout), api_key, environment)
    return FakeEchoRepairModel(
        ModelParameters("fake", "fake://local", "fake-echo-v1", 0.0, 4096, timeout)
    )


def _initial_record(case_id: str) -> dict[str, object]:
    paths = list((PHASE8_ARTIFACT_ROOT / "initial" / case_id).glob("*.json"))
    if len(paths) != 1:
        raise ValueError(f"expected one frozen Initial artifact for {case_id}")
    return json.loads(paths[0].read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    stage = parser.add_mutually_exclusive_group(required=True)
    stage.add_argument("--stage1", action="store_true")
    stage.add_argument("--stage2", action="store_true")
    parser.add_argument("--provider", choices=["deepseek", "fake"], default="deepseek")
    parser.add_argument("--confirm-phase8-stage1", action="store_true")
    parser.add_argument("--confirm-phase8-stage2", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.stage1 and args.confirm_phase8_stage2:
        parser.error("Stage 1 cannot accept the Stage 2 confirmation")
    if args.stage2 and args.confirm_phase8_stage1:
        parser.error("Stage 2 cannot accept the Stage 1 confirmation")
    if args.provider == "deepseek":
        required = (
            args.confirm_phase8_stage1 if args.stage1 else args.confirm_phase8_stage2
        )
        if not required:
            parser.error("explicit confirmation for the selected Phase 8 stage is required")
        if args.limit is not None:
            parser.error("formal Phase 8 stages cannot use --limit")
    try:
        preflight = validate_phase8_preflight()
        stage2 = validate_stage2_gate() if args.stage2 else None
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(f"Phase 8 frozen gate failed: {exc}")
    cases = list(preflight["cases"])
    if args.limit is not None:
        cases = cases[: args.limit]
    model = _model(args.provider, args.timeout)
    store = Phase8ArtifactStore(PHASE8_ARTIFACT_ROOT)
    partition_hash = preflight["partition"]["overall_manifest_hash"]

    if args.stage1:
        records = []
        expected_hashes = {
            item["case_id"]: item["prompt_hash"]
            for item in preflight["prompt_audit"]["prompt_records"]
        }
        for index, case in enumerate(cases, start=1):
            context = build_initial_context(
                case,
                preflight["fl_records"][case.case_id],
                preflight["runtime"].evaluations[case.case_id],
            )
            prompt = render_initial_prompt(
                context, set(case.metadata["phase8"]["base_test_ids"])
            )
            if prompt.prompt_hash != expected_hashes[case.case_id]:
                parser.error(f"Initial prompt hash mismatch for {case.case_id}")
            record = run_initial_attempt(
                case,
                prompt,
                model,
                evaluate_source,
                store,
                partition_hash,
                raw_runtime_manifest_hash=preflight["runtime"].validation[
                    "manifest_hash"
                ],
                resume=args.resume,
            )
            if isinstance(model, DeepSeekProvider):
                record = attach_provider_metadata(
                    store, record, model.consume_response_metadata()
                )
            records.append(record)
            print(
                f"[{index}/{len(cases)}] {case.case_id}: "
                f"{record['classification']}; eligible="
                f"{record.get('second_round_eligible', False)}",
                flush=True,
            )
        if args.provider == "deepseek":
            stage1_manifest, cohort = build_stage1_manifests(cases, records)
            _write_json(PHASE8_STAGE1_MANIFEST, stage1_manifest)
            _write_json(PHASE8_ELIGIBLE_COHORT, cohort)
            print(
                f"Stage 1 complete; eligible={cohort['eligible_count']}; "
                "Stage 2 was not started."
            )
        return 0

    cohort_by_case = {
        item["case_id"]: item for item in stage2["cohort"]["entries"]
    }
    eligible_cases = [case for case in cases if case.case_id in cohort_by_case]
    completed = 0
    for case in eligible_cases:
        context = build_initial_context(
            case,
            preflight["fl_records"][case.case_id],
            preflight["runtime"].evaluations[case.case_id],
        )
        initial_prompt = render_initial_prompt(
            context, set(case.metadata["phase8"]["base_test_ids"])
        )
        initial_record = _initial_record(case.case_id)
        for arm_value in second_round_order(case.case_id, PHASE8_RANDOM_SEED):
            arm = Phase8Arm(arm_value)
            record = run_second_attempt(
                case,
                initial_prompt,
                initial_record,
                arm,
                model,
                evaluate_source,
                store,
                partition_hash,
                resume=args.resume,
            )
            if isinstance(model, DeepSeekProvider):
                record = attach_provider_metadata(
                    store, record, model.consume_response_metadata()
                )
            completed += 1
            print(f"[{completed}/{len(eligible_cases) * 2}] {case.case_id}/{arm.value}")
    print(f"Stage 2 complete; paired calls={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
