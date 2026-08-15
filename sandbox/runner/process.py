"""Host process helpers shared by execution backends."""

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    stdout: str
    stderr: str
    time_ms: int
    timed_out: bool


def _decode(output: bytes | None) -> str:
    return (output or b"").decode("utf-8", errors="replace")


def run_process(
    command: list[str],
    *,
    timeout_seconds: float,
    cwd: Path,
    stdin_file: IO[bytes] | None = None,
    environment: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run a host process and kill its process group on timeout."""

    started_at = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=stdin_file,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=environment,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ProcessResult(
            exit_code=process.returncode,
            stdout=_decode(stdout),
            stderr=_decode(stderr),
            time_ms=round((time.perf_counter() - started_at) * 1000),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        return ProcessResult(
            exit_code=None,
            stdout=_decode(stdout),
            stderr=_decode(stderr),
            time_ms=round((time.perf_counter() - started_at) * 1000),
            timed_out=True,
        )
