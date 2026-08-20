"""Compile once and execute many inputs inside the existing Docker sandbox."""

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path

from analysis.sanitizer.analyzer import SANITIZER_COMPILE_FLAGS, SANITIZER_ENVIRONMENT
from analysis.sanitizer.parser import SanitizerParser
from sandbox.runner.config import RunnerConfig
from sandbox.runner.docker_executor import check_docker, run_container


STDERR_EXCERPT_BYTES = 8192


@dataclass(frozen=True)
class BatchObservation:
    duration_ms: int
    exit_code: int
    stderr_excerpt: str
    stderr_hash: str
    stderr_length: int
    stdout_hash: str
    stdout_length: int
    test_id: str
    timed_out: bool

    @property
    def sanitizer_findings(self) -> tuple[str, ...]:
        analyzers = {
            item.analyzer for item in SanitizerParser().parse(self.stderr_excerpt)
        }
        if "AddressSanitizer:DEADLYSIGNAL" in self.stderr_excerpt:
            analyzers.add("asan")
        return tuple(sorted(analyzers))


@dataclass(frozen=True)
class BatchResult:
    compile_exit_code: int
    compile_stderr_excerpt: str
    compile_stderr_hash: str
    compile_stderr_length: int
    observations: tuple[BatchObservation, ...]
    total_time_ms: int

    @property
    def compile_success(self) -> bool:
        return self.compile_exit_code == 0


def _decode(value: str) -> str:
    return base64.b64decode(value or "").decode("utf-8", errors="replace")


def parse_batch_output(output: str, test_ids: list[str], total_time_ms: int) -> BatchResult:
    compile_values = None
    observations = []
    for line in output.splitlines():
        values = line.split("\t")
        if values[0] == "COMPILE" and len(values) == 6:
            compile_values = values
        elif values[0] == "RUN" and len(values) == 10:
            index = int(values[1])
            observations.append(
                BatchObservation(
                    duration_ms=int(values[9]),
                    exit_code=int(values[2]),
                    stderr_excerpt=_decode(values[8]),
                    stderr_hash=values[6],
                    stderr_length=int(values[7]),
                    stdout_hash=values[4],
                    stdout_length=int(values[5]),
                    test_id=test_ids[index],
                    timed_out=values[3] == "true",
                )
            )
    if compile_values is None:
        raise ValueError("batch executor did not emit compile metadata")
    if int(compile_values[1]) == 0 and len(observations) != len(test_ids):
        raise ValueError(
            "batch executor did not emit every requested observation: "
            + repr(output[-2000:])
        )
    observations.sort(key=lambda item: test_ids.index(item.test_id))
    return BatchResult(
        compile_exit_code=int(compile_values[1]),
        compile_stderr_excerpt=_decode(compile_values[5]),
        compile_stderr_hash=compile_values[3],
        compile_stderr_length=int(compile_values[4]),
        observations=tuple(observations),
        total_time_ms=total_time_ms,
    )


_BATCH_SCRIPT = r'''#!/bin/bash
set +e

summarize_stderr() {
    local path="$1"
    local length
    length=$(wc -c < "$path")
    if [ "$length" -le 8192 ]; then
        base64 -w0 < "$path"
    else
        { head -c 4096 "$path"; printf '\n...[bounded]...\n'; tail -c 4096 "$path"; } | base64 -w0
    fi
}

hash_file() { sha256sum "$1" | cut -d' ' -f1; }

COMPILER=(gcc -std=c99 __FLAGS__ /workspace/main.c -lm -o /workspace/program)
"${COMPILER[@]}" > /workspace/compile.stdout 2> /workspace/compile.stderr
compile_exit=$?
printf 'COMPILE\t%s\t%s\t%s\t%s\t%s\n' \
    "$compile_exit" \
    "$(hash_file /workspace/compile.stdout)" \
    "$(hash_file /workspace/compile.stderr)" \
    "$(wc -c < /workspace/compile.stderr)" \
    "$(summarize_stderr /workspace/compile.stderr)"
if [ "$compile_exit" -ne 0 ]; then exit 0; fi

mkdir -p /workspace/results

run_one() {
    local input="$1"
    local name
    name=$(basename "$input" .in)
    local stdout_path="/workspace/run.${name}.stdout"
    local stderr_path="/workspace/run.${name}.stderr"
    start=$(date +%s%N)
    timeout --signal=TERM --kill-after=1s __RUN_TIMEOUT__s \
        /workspace/program < "$input" > "$stdout_path" 2> "$stderr_path"
    exit_code=$?
    end=$(date +%s%N)
    timed_out=false
    if [ "$exit_code" -eq 124 ] || [ "$exit_code" -eq 137 ]; then timed_out=true; fi
    printf 'RUN\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$((10#$name))" "$exit_code" "$timed_out" \
        "$(hash_file "$stdout_path")" \
        "$(wc -c < "$stdout_path")" \
        "$(hash_file "$stderr_path")" \
        "$(wc -c < "$stderr_path")" \
        "$(summarize_stderr "$stderr_path")" \
        "$(((end-start)/1000000))" > "/workspace/results/${name}.tsv"
    rm -f "$stdout_path" "$stderr_path"
}

active=0
for input in /workspace/inputs/*.in; do
    run_one "$input" &
    active=$((active + 1))
    if [ "$active" -ge 4 ]; then
        wait -n
        active=$((active - 1))
    fi
done
wait
cat /workspace/results/*.tsv
'''


class DockerBatchExecutor:
    def __init__(self, config: RunnerConfig | None = None) -> None:
        self.config = config or RunnerConfig()
        self._docker: str | None = None

    def run(
        self,
        source: str,
        inputs: list[tuple[str, str]],
        *,
        sanitizer: bool,
    ) -> BatchResult:
        if not inputs:
            raise ValueError("batch execution requires at least one input")
        with tempfile.TemporaryDirectory(prefix="codedoctor-phase9-") as temporary:
            work = Path(temporary).resolve()
            (work / "inputs").mkdir()
            (work / "main.c").write_text(source, encoding="utf-8")
            test_ids = []
            for index, (test_id, input_text) in enumerate(inputs):
                test_ids.append(test_id)
                (work / "inputs" / f"{index:06d}.in").write_text(
                    input_text, encoding="utf-8"
                )
            flags = SANITIZER_COMPILE_FLAGS if sanitizer else ("-O2",)
            script = _BATCH_SCRIPT.replace("__FLAGS__", " ".join(flags)).replace(
                "__RUN_TIMEOUT__", str(self.config.run_timeout_seconds)
            )
            (work / "batch.sh").write_text(script, encoding="utf-8")
            if self._docker is None:
                self._docker = check_docker(self.config, work)
            environment = (
                tuple(SANITIZER_ENVIRONMENT.items()) if sanitizer else ()
            )
            timeout = (
                self.config.compile_timeout_seconds
                + len(inputs) * (self.config.run_timeout_seconds + 1.5)
                + 20
            )
            process = run_container(
                self._docker,
                self.config,
                work,
                ["bash", "/workspace/batch.sh"],
                timeout,
                environment=environment,
            )
            if process.timed_out or process.exit_code != 0:
                raise RuntimeError(
                    "Phase 9 batch container failed: "
                    + (process.stderr or process.stdout)[-2000:]
                )
            return parse_batch_output(process.stdout, test_ids, process.time_ms)
