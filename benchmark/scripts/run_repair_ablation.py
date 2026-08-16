"""Run one-attempt A/B/C repair with exact cache/resume semantics."""

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    DEEPSEEK_EXPERIMENT_CONFIG,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_PILOT_FL,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.artifacts import ArtifactStore  # noqa: E402
from repair.context import load_fl_records  # noqa: E402
from repair.deepseek import (  # noqa: E402
    BASE_URL as DEEPSEEK_BASE_URL,
    MAX_TOKENS as DEEPSEEK_MAX_TOKENS,
    MODEL as DEEPSEEK_MODEL,
    DeepSeekProvider,
    artifact_root_for_role,
    attach_response_metadata,
    model_parameters as deepseek_model_parameters,
    resolve_api_key as resolve_deepseek_api_key,
    validate_configuration as validate_deepseek_configuration,
)
from repair.evaluator import evaluate_source  # noqa: E402
from repair.models import EvidenceGroup, ModelParameters  # noqa: E402
from repair.pipeline import run_repair_attempt  # noqa: E402
from repair.protocol import (  # noqa: E402
    bulk_confirmation_required,
    unconfirmed_online_call_limit,
    validate_repair_protocol,
)
from repair.provider import (  # noqa: E402
    FakeEchoRepairModel,
    OpenAICompatibleProvider,
)


def _selected_groups(values: list[str] | None) -> list[EvidenceGroup]:
    if not values:
        return list(EvidenceGroup)
    return [EvidenceGroup(value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", action="append", default=[])
    parser.add_argument("--group", action="append", choices=["A", "B", "C"])
    parser.add_argument(
        "--provider",
        choices=["deepseek", "openai-compatible", "fake"],
        default="openai-compatible",
    )
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--confirm-bulk",
        action="store_true",
        help="confirm explicit user approval beyond the provider smoke limit",
    )
    args = parser.parse_args()
    validate_repair_protocol()

    if args.provider == "deepseek":
        validate_deepseek_configuration(DEEPSEEK_EXPERIMENT_CONFIG)
        if args.model not in {None, DEEPSEEK_MODEL}:
            parser.error(f"DeepSeek model is frozen as {DEEPSEEK_MODEL}")
        if args.base_url not in {None, DEEPSEEK_BASE_URL}:
            parser.error(f"DeepSeek base URL is frozen as {DEEPSEEK_BASE_URL}")
        if args.temperature is not None:
            parser.error("DeepSeek thinking mode does not send temperature")
        if args.max_tokens not in {None, DEEPSEEK_MAX_TOKENS}:
            parser.error(
                f"DeepSeek max tokens is frozen as {DEEPSEEK_MAX_TOKENS}"
            )
        if args.seed is not None:
            parser.error("DeepSeek thinking mode does not use a seed control")
        api_key, credential_environment = resolve_deepseek_api_key(os.environ)
        if not api_key or not credential_environment:
            parser.error("DeepSeek API credential unavailable")
        parameters = deepseek_model_parameters(args.timeout)
        model = DeepSeekProvider(parameters, api_key, credential_environment)
    else:
        model_name = (
            args.model
            or os.environ.get("CODEDOCTOR_MODEL")
            or os.environ.get("OPENAI_MODEL")
        )
        base_url = (
            args.base_url
            or os.environ.get("CODEDOCTOR_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
        api_key = os.environ.get("CODEDOCTOR_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        temperature = 0.0 if args.temperature is None else args.temperature
        max_tokens = 4096 if args.max_tokens is None else args.max_tokens
    if args.provider == "fake":
        model_name = model_name or "fake-echo-v1"
        base_url = base_url or "fake://local"
    elif args.provider == "openai-compatible" and (
        not model_name or not base_url or not api_key
    ):
        parser.error(
            "online provider requires model, base URL, and CODEDOCTOR_API_KEY or OPENAI_API_KEY"
        )
    if args.provider != "deepseek":
        parameters = ModelParameters(
            provider=args.provider,
            base_url=base_url,
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=args.timeout,
            seed=args.seed,
        )
        model = (
            FakeEchoRepairModel(parameters)
            if args.provider == "fake"
            else OpenAICompatibleProvider(parameters, api_key)
        )
    requested = {
        item.strip()
        for value in args.cases
        for item in value.split(",")
        if item.strip()
    }
    cases = list(load_manifest(CODEFLAWS_REPAIR_PILOT))
    if requested:
        cases = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in cases}
        if missing:
            parser.error(f"unknown Repair Pilot cases: {sorted(missing)}")
    if args.limit is not None:
        cases = cases[: args.limit]

    groups = _selected_groups(args.group)
    expected_calls = len(cases) * len(groups)
    if bulk_confirmation_required(
        args.provider, expected_calls, args.confirm_bulk
    ):
        limit = unconfirmed_online_call_limit(args.provider)
        parser.error(
            f"online run would make {expected_calls} calls, exceeding the "
            f"unconfirmed limit of {limit}; explicit user approval and "
            "--confirm-bulk are required"
        )

    fl_records = load_fl_records(REPAIR_PILOT_FL)
    experiment_role = (
        "formal_evidence_ablation"
        if args.provider == "deepseek" and args.confirm_bulk
        else "pre_experiment_smoke"
    )
    artifact_root = (
        artifact_root_for_role(REPAIR_ARTIFACT_ROOT, experiment_role)
        if args.provider == "deepseek"
        else REPAIR_ARTIFACT_ROOT
    )
    store = ArtifactStore(artifact_root)
    completed = 0
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] baseline {case.case_id}", flush=True)
        baseline = evaluate_source(case, case.get_buggy_source(), include_validation=False)
        for group in groups:
            result = run_repair_attempt(
                case,
                group,
                model,
                fl_records.get(case.case_id),
                baseline,
                store,
                resume=args.resume,
                experimental=args.provider != "fake",
            )
            if isinstance(model, DeepSeekProvider):
                result = attach_response_metadata(
                    store,
                    result,
                    model.consume_response_metadata(),
                    experiment_role,
                )
            completed += 1
            print(f"  {group.value}: {result['classification']}", flush=True)
    print(f"completed {completed} single-attempt artifacts")
    if isinstance(model, DeepSeekProvider):
        print(
            f"DeepSeek requests attempted={model.requests_attempted}; "
            f"responses received={model.responses_received}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
