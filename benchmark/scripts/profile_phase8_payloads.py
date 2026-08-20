"""Attribute the superseded v1 Initial payload bytes before bounded rendering."""

import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.config import (  # noqa: E402
    PHASE8_EVALUATION_SET,
    PHASE8_FL,
    PHASE8_PAYLOAD_ATTRIBUTION,
    PHASE8_PROMPT_AUDIT_V1,
)
from benchmark.models import load_manifest  # noqa: E402
from repair.deepseek import DeepSeekProvider, model_parameters  # noqa: E402
from repair_phase8.context import build_initial_context  # noqa: E402
from repair_phase8.models import Phase8Arm, Phase8Prompt  # noqa: E402
from repair_phase8.partition import canonical_hash  # noqa: E402
from repair_phase8.runtime_evidence import load_phase8_runtime  # noqa: E402


SYSTEM = (
    "You repair buggy C or C++ programs. Return only the complete repaired source "
    "code. Do not return an explanation."
)
VERSION = "phase8-initial-v1"


def _bytes(value: str) -> int:
    return len(value.encode("utf-8"))


def _example(item: object) -> str:
    return (
        f"### {item.test_id}\nInput:\n```text\n{item.input_text}\n```\n"
        f"Expected output:\n```text\n{item.expected_output}\n```"
    )


def _fl(context: object) -> str:
    if not context.suspicious_locations:
        return (
            "## CodeDoctor FL-v1 suspicious locations\n"
            "No reliable suspicious location is available from FL-v1."
        )
    rows = []
    for item in context.suspicious_locations:
        tie = (
            f", tie=[{item.tie_start_rank},{item.tie_end_rank}]"
            if item.tie_end_rank > item.tie_start_rank
            else ""
        )
        branch = "n/a" if item.branch_score is None else f"{item.branch_score:.6g}"
        rows.append(
            f"- rank {item.rank}: line {item.line}, line_score={item.line_score:.6g}, "
            f"branch_score={branch}{tie}: {item.source_line}"
        )
    return "## CodeDoctor FL-v1 suspicious locations\n" + "\n".join(rows)


def _runtime(context: object) -> str:
    parts = ["## Frozen buggy runtime evidence"]
    for item in context.execution_evidence:
        parts.extend(
            (
                f"### {item.test_id}: {item.verdict}",
                f"Actual stdout:\n```text\n{item.actual_stdout}\n```",
                f"stderr:\n```text\n{item.stderr}\n```",
                f"Exit code: {item.exit_code}; timed out: {str(item.timed_out).lower()}",
            )
        )
    return "\n".join(parts)


def _prompt(context: object, base_ids: set[str]) -> tuple[Phase8Prompt, dict[str, int]]:
    base = [item for item in context.task_examples if item.test_id in base_ids]
    feedback = [item for item in context.task_examples if item.test_id not in base_ids]
    base_oracle = (
        "\n".join(_example(item) for item in base)
        if base
        else "No original Base Repair Tests are available for this case."
    )
    feedback_oracle = "\n".join(_example(item) for item in feedback)
    fl = _fl(context)
    runtime = _runtime(context)
    source = context.buggy_source.rstrip()
    user = f"""Repair the following buggy C/C++ program.

Requirements:
- Make the smallest reasonable change that repairs the program.
- Preserve the existing input/output protocol.
- Do not hard-code the supplied test cases or expected outputs.
- Return the complete compilable source code and no explanatory prose.

## Buggy source
```{'cpp' if '++' in context.language else 'c'}
{source}
```

## Base repair-time oracle
{base_oracle}

## Feedback-test repair-time oracle
These input/expected-output examples are public before the first repair attempt.
{feedback_oracle}

{fl}

{runtime}"""
    digest = hashlib.sha256((VERSION + "\0" + SYSTEM + "\0" + user).encode()).hexdigest()
    prompt = Phase8Prompt(VERSION, Phase8Arm.INITIAL, SYSTEM, user, digest)
    stdout_bytes = sum(_bytes(item.actual_stdout) for item in context.execution_evidence)
    stderr_bytes = sum(_bytes(item.stderr) for item in context.execution_evidence)
    runtime_metadata = _bytes(runtime) - stdout_bytes - stderr_bytes
    components = {
        "base_oracle_bytes": _bytes(base_oracle),
        "buggy_source_bytes": _bytes(source),
        "feedback_oracle_bytes": _bytes(feedback_oracle),
        "fl_bytes": _bytes(fl),
        "runtime_metadata_bytes": runtime_metadata,
        "runtime_stderr_bytes": stderr_bytes,
        "runtime_stdout_bytes": stdout_bytes,
    }
    components["instruction_template_bytes"] = (
        _bytes(SYSTEM) + _bytes(user) - sum(components.values())
    )
    return prompt, components


def main() -> int:
    cases = list(load_manifest(PHASE8_EVALUATION_SET))
    runtime = load_phase8_runtime(cases)
    fl = {
        item["case_id"]: item
        for item in map(json.loads, PHASE8_FL.read_text(encoding="utf-8").splitlines())
    }
    provider = DeepSeekProvider(
        model_parameters(120.0), "offline-placeholder", "DEEPSEEK_API_KEY"
    )
    rows = []
    for case in cases:
        context = build_initial_context(
            case, fl[case.case_id], runtime.evaluations[case.case_id]
        )
        prompt, components = _prompt(
            context, set(case.metadata["phase8"]["base_test_ids"])
        )
        serialized = json.dumps(
            provider.request_payload(prompt),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        total = _bytes(serialized)
        content_bytes = _bytes(prompt.system) + _bytes(prompt.user)
        row = {
            "case_id": case.case_id,
            **components,
            "oracle_oversize": (
                components["base_oracle_bytes"]
                + components["feedback_oracle_bytes"]
                > 400_000
            ),
            "serialization_overhead_bytes": total - content_bytes,
            "total_payload_bytes": total,
        }
        if sum(
            value
            for key, value in row.items()
            if key.endswith("_bytes") and key != "total_payload_bytes"
        ) != total:
            raise ValueError(f"component attribution does not sum for {case.case_id}")
        rows.append(row)
    previous = json.loads(PHASE8_PROMPT_AUDIT_V1.read_text(encoding="utf-8"))
    oversized = [row for row in rows if row["total_payload_bytes"] > 400_000]
    value = {
        "attribution_version": "phase8-payload-byte-attribution-v1",
        "canonical_encoding": "UTF-8",
        "case_count": len(rows),
        "component_records": rows,
        "hard_gate_bytes": 400_000,
        "oversized_case_count": len(oversized),
        "oversized_cases": oversized,
        "superseded_prompt_set_hash": previous["prompt_set_hash"],
    }
    value["overall_attribution_hash"] = canonical_hash(value)
    PHASE8_PAYLOAD_ATTRIBUTION.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {PHASE8_PAYLOAD_ATTRIBUTION}; oversized={len(oversized)}; "
        f"max={max(row['total_payload_bytes'] for row in rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
