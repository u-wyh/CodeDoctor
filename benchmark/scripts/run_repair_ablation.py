"""Run one-attempt A/B/C repair with exact cache/resume semantics."""

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    CODEFLAWS_REPAIR_PILOT,
    REPAIR_ARTIFACT_ROOT,
    REPAIR_PILOT_FL,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.artifacts import ArtifactStore  # noqa: E402
from repair.context import load_fl_records  # noqa: E402
from repair.evaluator import evaluate_source  # noqa: E402
from repair.models import EvidenceGroup, ModelParameters  # noqa: E402
from repair.pipeline import run_repair_attempt  # noqa: E402
from repair.protocol import validate_repair_protocol  # noqa: E402
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
    parser.add_argument("--provider", choices=["openai-compatible", "fake"], default="openai-compatible")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    validate_repair_protocol()

    model_name = args.model or os.environ.get("CODEDOCTOR_MODEL") or os.environ.get("OPENAI_MODEL")
    base_url = args.base_url or os.environ.get("CODEDOCTOR_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("CODEDOCTOR_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if args.provider == "fake":
        model_name = model_name or "fake-echo-v1"
        base_url = base_url or "fake://local"
    elif not model_name or not base_url or not api_key:
        parser.error(
            "online provider requires model, base URL, and CODEDOCTOR_API_KEY or OPENAI_API_KEY"
        )
    parameters = ModelParameters(
        provider=args.provider,
        base_url=base_url,
        model=model_name,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
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

    fl_records = load_fl_records(REPAIR_PILOT_FL)
    store = ArtifactStore(REPAIR_ARTIFACT_ROOT)
    completed = 0
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] baseline {case.case_id}", flush=True)
        baseline = evaluate_source(case, case.get_buggy_source(), include_validation=False)
        for group in _selected_groups(args.group):
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
            completed += 1
            print(f"  {group.value}: {result['classification']}", flush=True)
    print(f"completed {completed} single-attempt artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
