"""Versioned A/B/C prompt rendering with a narrow repair-time input type."""

import hashlib

from .models import EvidenceGroup, PromptDocument, RepairContext


PROMPT_TEMPLATE_VERSION = "repair-evidence-v1"
SYSTEM_PROMPT = (
    "You repair buggy C or C++ programs. Return only the complete repaired source "
    "code. Do not return an explanation."
)
BASE_INSTRUCTION = """Repair the following buggy C/C++ program.

Requirements:
- Make the smallest reasonable change that repairs the program.
- Preserve the existing input/output protocol.
- Do not hard-code the supplied test cases or expected outputs.
- Return the complete compilable source code and no explanatory prose.

## Buggy source
```{language}
{source}
```"""


def _fl_section(context: RepairContext) -> str:
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


def _execution_section(context: RepairContext) -> str:
    sections = ["## Repair-test execution evidence"]
    for item in context.execution_evidence:
        sections.extend(
            (
                f"### {item.test_id}: {item.verdict}",
                f"Input:\n```text\n{item.input_text}\n```",
                f"Expected output:\n```text\n{item.expected_output}\n```",
                f"Actual stdout:\n```text\n{item.actual_stdout}\n```",
                f"stderr:\n```text\n{item.stderr}\n```",
                f"Exit code: {item.exit_code}; timed out: {str(item.timed_out).lower()}",
            )
        )
    return "\n".join(sections)


def render_prompt(context: RepairContext, group: EvidenceGroup) -> PromptDocument:
    if group is EvidenceGroup.SOURCE_ONLY:
        if context.suspicious_locations or context.execution_evidence:
            raise ValueError("Group A context must contain source only")
    elif group is EvidenceGroup.SOURCE_FL:
        if not context.suspicious_locations or context.execution_evidence:
            raise ValueError("Group B requires FL and forbids execution evidence")
    elif group is EvidenceGroup.SOURCE_FL_EXECUTION:
        if not context.suspicious_locations or not context.execution_evidence:
            raise ValueError("Group C requires FL and execution evidence")

    user = BASE_INSTRUCTION.format(
        language="cpp" if "++" in context.language else "c",
        source=context.buggy_source.rstrip(),
    )
    if group in {EvidenceGroup.SOURCE_FL, EvidenceGroup.SOURCE_FL_EXECUTION}:
        user += "\n\n" + _fl_section(context)
    if group is EvidenceGroup.SOURCE_FL_EXECUTION:
        user += "\n\n" + _execution_section(context)
    digest = hashlib.sha256(
        (PROMPT_TEMPLATE_VERSION + "\0" + SYSTEM_PROMPT + "\0" + user).encode()
    ).hexdigest()
    return PromptDocument(
        template_version=PROMPT_TEMPLATE_VERSION,
        group=group,
        system=SYSTEM_PROMPT,
        user=user,
        prompt_hash=digest,
    )
