"""Versioned Phase 8 Initial/R/F prompt rendering."""

import hashlib

from repair.models import RepairContext

from .models import Phase8Arm, Phase8Prompt


SYSTEM_PROMPT = (
    "You repair buggy C or C++ programs. Return only the complete repaired source "
    "code. Do not return an explanation."
)
INITIAL_VERSION = "phase8-initial-v1"
RETRY_VERSION = "phase8-retry-control-v1"
FEEDBACK_VERSION = "phase8-feedback-v1"
SECOND_INSTRUCTION = """Your previous candidate patch did not complete the repair process.
Review the original task and your previous patch carefully.
Produce one revised complete source program."""


def _digest(version: str, system: str, user: str) -> str:
    return hashlib.sha256((version + "\0" + system + "\0" + user).encode()).hexdigest()


def _example(item: object) -> str:
    return (
        f"### {item.test_id}\nInput:\n```text\n{item.input_text}\n```\n"
        f"Expected output:\n```text\n{item.expected_output}\n```"
    )


def _fl(context: RepairContext) -> str:
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


def _buggy_runtime(context: RepairContext) -> str:
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


def render_initial_prompt(context: RepairContext, base_test_ids: set[str]) -> Phase8Prompt:
    if not context.task_examples or context.fl_status is None or not context.execution_evidence:
        raise ValueError("Phase 8 Initial requires oracle, FL-v1, and frozen runtime")
    base = [item for item in context.task_examples if item.test_id in base_test_ids]
    feedback = [item for item in context.task_examples if item.test_id not in base_test_ids]
    if not feedback:
        raise ValueError("Phase 8 Initial requires at least one Feedback test")
    base_oracle = (
        chr(10).join(_example(item) for item in base)
        if base
        else "No original Base Repair Tests are available for this case."
    )
    user = f"""Repair the following buggy C/C++ program.

Requirements:
- Make the smallest reasonable change that repairs the program.
- Preserve the existing input/output protocol.
- Do not hard-code the supplied test cases or expected outputs.
- Return the complete compilable source code and no explanatory prose.

## Buggy source
```{'cpp' if '++' in context.language else 'c'}
{context.buggy_source.rstrip()}
```

## Base repair-time oracle
{base_oracle}

## Feedback-test repair-time oracle
These input/expected-output examples are public before the first repair attempt.
{chr(10).join(_example(item) for item in feedback)}

{_fl(context)}

{_buggy_runtime(context)}"""
    return Phase8Prompt(
        INITIAL_VERSION,
        Phase8Arm.INITIAL,
        SYSTEM_PROMPT,
        user,
        _digest(INITIAL_VERSION, SYSTEM_PROMPT, user),
    )


def _feedback_section(feedback: dict[str, object]) -> str:
    compile_value = feedback.get("compile")
    if compile_value is not None:
        return (
            "## Failed repair-time execution feedback\n"
            f"Compiler exit status: {compile_value['exit_code']}\n"
            f"Compiler stderr:\n```text\n{compile_value['stderr']}\n```"
        )
    parts = ["## Failed repair-time execution feedback"]
    for item in feedback["failed_tests"]:
        parts.extend(
            (
                f"### {item['test_id']}: FAIL",
                f"Input:\n```text\n{item['input']}\n```",
                f"Expected output:\n```text\n{item['expected_output']}\n```",
                f"Actual output:\n```text\n{item['actual_stdout']}\n```",
                f"stderr:\n```text\n{item['stderr']}\n```",
                f"Exit code: {item['exit_code']}; timed out: "
                f"{str(item['timed_out']).lower()}; verdict: {item['verdict']}",
            )
        )
    return "\n".join(parts)


def render_second_prompt(
    initial: Phase8Prompt,
    previous_patch: str,
    arm: Phase8Arm,
    feedback: dict[str, object] | None = None,
) -> Phase8Prompt:
    if arm not in {Phase8Arm.RETRY_CONTROL, Phase8Arm.FEEDBACK}:
        raise ValueError("second-round arm must be retry_control or feedback")
    if arm is Phase8Arm.RETRY_CONTROL and feedback is not None:
        raise ValueError("Retry Control forbids execution feedback")
    if arm is Phase8Arm.FEEDBACK and feedback is None:
        raise ValueError("Feedback arm requires failed execution feedback")
    user = (
        initial.user
        + "\n\n## Previous candidate patch\n```c\n"
        + previous_patch.rstrip()
        + "\n```\n\n## Second repair instruction\n"
        + SECOND_INSTRUCTION
    )
    version = RETRY_VERSION if arm is Phase8Arm.RETRY_CONTROL else FEEDBACK_VERSION
    if feedback is not None:
        user += "\n\n" + _feedback_section(feedback)
    return Phase8Prompt(
        version,
        arm,
        SYSTEM_PROMPT,
        user,
        _digest(version, SYSTEM_PROMPT, user),
    )
