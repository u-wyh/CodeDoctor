"""Deterministic bounded rendering of public or execution evidence."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


RENDER_PROTOCOL_VERSION = "phase8-runtime-evidence-render-v2"
ORACLE_RENDER_VERSION = "phase8-common-oracle-render-v2"
ORACLE_FULL_BYTES = 4096
ORACLE_PREFIX_BYTES = 2048
ORACLE_SUFFIX_BYTES = 2048
STDOUT_FULL_BYTES = 4096
STDOUT_PREFIX_BYTES = 2048
STDOUT_SUFFIX_BYTES = 2048
STDERR_FULL_BYTES = 8192
STDERR_PREFIX_BYTES = 4096
STDERR_SUFFIX_BYTES = 4096
COMPILER_FULL_BYTES = 16384
COMPILER_PREFIX_BYTES = 8192
COMPILER_SUFFIX_BYTES = 8192
MISMATCH_CONTEXT_BEFORE_BYTES = 1024
MISMATCH_CONTEXT_AFTER_BYTES = 3072


@dataclass(frozen=True)
class RenderedEvidence:
    text: str
    raw_hash: str
    rendered_hash: str


def canonical_bytes(value: str) -> bytes:
    return value.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return sha256_bytes(payload)


def _field(value: object, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _bounded_body(
    value: bytes,
    *,
    full_bytes: int,
    prefix_bytes: int,
    suffix_bytes: int,
) -> tuple[str, bool, int]:
    if len(value) <= full_bytes:
        return _decode(value), False, 0
    omitted = len(value) - prefix_bytes - suffix_bytes
    body = (
        _decode(value[:prefix_bytes])
        + f"\n...[omitted {omitted} bytes]...\n"
        + _decode(value[-suffix_bytes:])
    )
    return body, True, omitted


def render_bounded_field(
    label: str,
    value: str,
    *,
    full_bytes: int,
    prefix_bytes: int,
    suffix_bytes: int,
) -> str:
    raw = canonical_bytes(value)
    body, truncated, omitted = _bounded_body(
        raw,
        full_bytes=full_bytes,
        prefix_bytes=prefix_bytes,
        suffix_bytes=suffix_bytes,
    )
    return (
        f"{label}_bytes: {len(raw)}\n"
        f"{label}_sha256: {sha256_bytes(raw)}\n"
        f"{label}_truncated: {str(truncated).lower()}\n"
        f"{label}_omitted_bytes: {omitted}\n"
        f"{label}:\n```text\n{body}\n```"
    )


def render_oracle_example(item: object) -> str:
    return "\n".join(
        (
            f"### {_field(item, 'test_id')}",
            render_bounded_field(
                "input",
                str(_field(item, "input_text")),
                full_bytes=ORACLE_FULL_BYTES,
                prefix_bytes=ORACLE_PREFIX_BYTES,
                suffix_bytes=ORACLE_SUFFIX_BYTES,
            ),
            render_bounded_field(
                "expected_output",
                str(_field(item, "expected_output")),
                full_bytes=ORACLE_FULL_BYTES,
                prefix_bytes=ORACLE_PREFIX_BYTES,
                suffix_bytes=ORACLE_SUFFIX_BYTES,
            ),
        )
    )


def render_oracle_examples(items: Iterable[object]) -> tuple[str, str]:
    text = "\n".join(render_oracle_example(item) for item in items)
    return text, sha256_bytes(canonical_bytes(text))


def first_differing_byte(expected: bytes, actual: bytes) -> int | None:
    common = min(len(expected), len(actual))
    for index in range(common):
        if expected[index] != actual[index]:
            return index
    return common if len(expected) != len(actual) else None


def _mismatch_body(actual: bytes, expected: bytes) -> str:
    offset = first_differing_byte(expected, actual)
    if offset is None:
        raise ValueError("mismatch rendering requires different byte sequences")
    start = max(0, offset - MISMATCH_CONTEXT_BEFORE_BYTES)
    end = min(len(actual), offset + MISMATCH_CONTEXT_AFTER_BYTES)
    window = actual[start:end]
    return "\n".join(
        (
            f"first_differing_byte_offset: {offset}",
            f"expected_total_bytes: {len(expected)}",
            f"expected_sha256: {sha256_bytes(expected)}",
            f"actual_window_start: {start}",
            f"actual_window_end: {end}",
            f"actual_window_omitted_before_bytes: {start}",
            f"actual_window_omitted_after_bytes: {len(actual) - end}",
            f"actual_mismatch_window:\n```text\n{_decode(window)}\n```",
        )
    )


def _observation_record(item: object) -> dict[str, object]:
    return {
        "actual_stdout": str(_field(item, "actual_stdout")),
        "exit_code": _field(item, "exit_code"),
        "stderr": str(_field(item, "stderr")),
        "test_id": str(_field(item, "test_id")),
        "timed_out": bool(_field(item, "timed_out")),
        "verdict": str(_field(item, "verdict")),
    }


def _render_observation(item: object, expected_output: str) -> str:
    record = _observation_record(item)
    actual = canonical_bytes(str(record["actual_stdout"]))
    expected = canonical_bytes(expected_output)
    stderr = canonical_bytes(str(record["stderr"]))
    summary = [
        f"### {record['test_id']}: {record['verdict']}",
        f"exit_code: {record['exit_code']}",
        f"timed_out: {str(record['timed_out']).lower()}",
        f"stdout_bytes: {len(actual)}",
        f"stdout_sha256: {sha256_bytes(actual)}",
        f"stderr_bytes: {len(stderr)}",
        f"stderr_sha256: {sha256_bytes(stderr)}",
    ]
    if record["verdict"] == "PASS" and actual == expected:
        summary.append("stdout_representation: matches expected output exactly")
    elif record["exit_code"] == 0 and not record["timed_out"] and actual != expected:
        summary.extend(("stdout_representation: first-difference", _mismatch_body(actual, expected)))
    else:
        body, truncated, omitted = _bounded_body(
            actual,
            full_bytes=STDOUT_FULL_BYTES,
            prefix_bytes=STDOUT_PREFIX_BYTES,
            suffix_bytes=STDOUT_SUFFIX_BYTES,
        )
        summary.extend(
            (
                "stdout_representation: prefix-suffix",
                f"stdout_truncated: {str(truncated).lower()}",
                f"stdout_omitted_bytes: {omitted}",
                f"stdout_content:\n```text\n{body}\n```",
            )
        )
    stderr_body, stderr_truncated, stderr_omitted = _bounded_body(
        stderr,
        full_bytes=STDERR_FULL_BYTES,
        prefix_bytes=STDERR_PREFIX_BYTES,
        suffix_bytes=STDERR_SUFFIX_BYTES,
    )
    summary.extend(
        (
            f"stderr_truncated: {str(stderr_truncated).lower()}",
            f"stderr_omitted_bytes: {stderr_omitted}",
            f"stderr_content:\n```text\n{stderr_body}\n```",
        )
    )
    return "\n".join(summary)


def render_execution_evidence(
    observations: Iterable[object],
    expected_by_test: Mapping[str, str],
    *,
    heading: str,
) -> RenderedEvidence:
    records = [_observation_record(item) for item in observations]
    sections = [heading]
    for item in records:
        test_id = str(item["test_id"])
        if test_id not in expected_by_test:
            raise ValueError(f"missing public expected output for {test_id}")
        sections.append(_render_observation(item, expected_by_test[test_id]))
    text = "\n".join(sections)
    return RenderedEvidence(
        text=text,
        raw_hash=_canonical_hash(records),
        rendered_hash=sha256_bytes(canonical_bytes(text)),
    )


def render_failed_feedback(feedback: Mapping[str, object]) -> RenderedEvidence:
    compile_value = feedback.get("compile")
    if isinstance(compile_value, Mapping):
        stderr = str(compile_value.get("stderr", ""))
        raw = {
            "compile": {
                "exit_code": compile_value.get("exit_code"),
                "stderr": stderr,
            }
        }
        text = "\n".join(
            (
                "## Failed repair-time execution feedback",
                f"compiler_exit_code: {compile_value.get('exit_code')}",
                render_bounded_field(
                    "compiler_stderr",
                    stderr,
                    full_bytes=COMPILER_FULL_BYTES,
                    prefix_bytes=COMPILER_PREFIX_BYTES,
                    suffix_bytes=COMPILER_SUFFIX_BYTES,
                ),
            )
        )
        return RenderedEvidence(
            text, _canonical_hash(raw), sha256_bytes(canonical_bytes(text))
        )
    failed = feedback.get("failed_tests")
    if not isinstance(failed, list):
        raise ValueError("failed feedback requires a failed_tests list")
    expected = {
        str(item["test_id"]): str(item["expected_output"])
        for item in failed
        if isinstance(item, Mapping)
    }
    return render_execution_evidence(
        failed,
        expected,
        heading="## Failed repair-time execution feedback",
    )
