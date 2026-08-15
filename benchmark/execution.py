"""Reproduce Codeflaws cases with their Makefiles inside the Docker sandbox."""

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from sandbox.runner.config import RunnerConfig
from sandbox.runner.docker_executor import (
    DockerBackendError,
    check_docker,
    run_container,
)
from sandbox.runner.process import ProcessResult

from .config import (
    BENCHMARK_COMPILE_TIMEOUT_SECONDS,
    BENCHMARK_RUN_TIMEOUT_SECONDS,
    PROJECT_ROOT,
)
from .models import BenchmarkCase, BenchmarkTest, ProgramArtifact


@dataclass(frozen=True)
class CompileVerification:
    success: bool
    exit_code: int | None
    timed_out: bool
    time_ms: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SuiteVerification:
    total: int
    passed: int
    failed: int
    timed_out: int
    runtime_errors: int
    first_failure: str | None

    @property
    def success(self) -> bool:
        return self.total > 0 and self.passed == self.total


@dataclass(frozen=True)
class CaseVerification:
    case_id: str
    defect_class: str
    buggy_compile: CompileVerification
    reference_compile: CompileVerification
    reference_repair: SuiteVerification | None
    reference_validation: SuiteVerification | None
    buggy_repair: SuiteVerification | None
    buggy_validation: SuiteVerification | None
    reproducible: bool
    exclusion_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return json.loads(json.dumps(asdict(self)))


@dataclass(frozen=True)
class _TestResult:
    test_id: str
    passed: bool
    timed_out: bool
    runtime_error: bool


def _trim_log(value: str, limit: int = 8000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _compile_result(result: ProcessResult) -> CompileVerification:
    return CompileVerification(
        success=not result.timed_out and result.exit_code == 0,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        time_ms=result.time_ms,
        stdout=_trim_log(result.stdout),
        stderr=_trim_log(result.stderr),
    )


def _empty_compile(reason: str) -> CompileVerification:
    return CompileVerification(False, None, False, 0, "", reason)


def _project_path(relative: str) -> Path:
    path = (PROJECT_ROOT / relative).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"benchmark path escapes project root: {relative}")
    return path


def _compile_program(
    docker: str,
    config: RunnerConfig,
    case: BenchmarkCase,
    artifact: ProgramArtifact,
    work_dir: Path,
) -> tuple[CompileVerification, Path]:
    source = _project_path(artifact.source_path)
    makefile = _project_path(str(case.metadata["makefile_path"]))
    shutil.copy2(source, work_dir / source.name)
    shutil.copy2(makefile, work_dir / "Makefile")
    result = run_container(
        docker,
        config,
        work_dir,
        ["make", "--no-print-directory", f"FILENAME={source.stem}"],
        BENCHMARK_COMPILE_TIMEOUT_SECONDS,
    )
    return _compile_result(result), work_dir / source.stem


def script_strips_leading_space(case: BenchmarkCase, suite: str) -> bool:
    key = (
        "repair_test_script_path"
        if suite == "repair"
        else "validation_test_script_path"
    )
    path_value = case.metadata.get(key)
    if not path_value:
        return True
    script = _project_path(str(path_value)).read_text(
        encoding="utf-8", errors="replace"
    )
    return "s/^[ " in script


def outputs_equivalent(
    actual: bytes, expected: bytes, *, strip_leading_space: bool
) -> bool:
    """Apply Codeflaws' sed normalization and trailing-space comparison."""

    actual_lines = actual.decode("utf-8", errors="replace").splitlines()
    expected_lines = expected.decode("utf-8", errors="replace").splitlines()
    normalized_actual = []
    for line in actual_lines:
        if line == "":
            continue
        if strip_leading_space:
            line = line.lstrip(" \t")
        normalized_actual.append(line.rstrip(" \t\r"))
    normalized_expected = [line.rstrip(" \t\r") for line in expected_lines]
    return normalized_actual == normalized_expected


def _run_suite(
    docker: str,
    config: RunnerConfig,
    case: BenchmarkCase,
    executable: Path,
    tests: Iterable[BenchmarkTest],
    suite: str,
    work_dir: Path,
) -> SuiteVerification:
    selected = tuple(tests)
    suite_dir = work_dir / f"{suite}-suite"
    inputs_dir = suite_dir / "inputs"
    results_dir = suite_dir / "results"
    inputs_dir.mkdir(parents=True)
    results_dir.mkdir()
    target = suite_dir / "program"
    shutil.copy2(executable, target)
    target.chmod(0o755)

    for index, test in enumerate(selected):
        if test.input_path is None:
            continue
        shutil.copyfile(_project_path(test.input_path), inputs_dir / f"{index:06d}.in")

    script = (
        "for input in /workspace/inputs/*.in; do "
        "id=${input##*/}; id=${id%.in}; "
        f"timeout -k 1s {BENCHMARK_RUN_TIMEOUT_SECONDS}s /workspace/program "
        ' < "$input" > "/workspace/results/$id.out" '
        '2> "/workspace/results/$id.err"; '
        'printf "%s\\n" "$?" > "/workspace/results/$id.status"; '
        "done"
    )
    overall_timeout = max(
        10.0,
        len(selected) * (BENCHMARK_RUN_TIMEOUT_SECONDS + 1.25) + 10.0,
    )
    container = run_container(
        docker,
        config,
        suite_dir,
        ["/bin/sh", "-c", script],
        overall_timeout,
    )
    strip_leading = script_strips_leading_space(case, suite)
    results: list[_TestResult] = []
    for index, test in enumerate(selected):
        prefix = results_dir / f"{index:06d}"
        status_path = prefix.with_suffix(".status")
        output_path = prefix.with_suffix(".out")
        if container.timed_out or not status_path.is_file() or not output_path.is_file():
            results.append(_TestResult(test.test_id, False, container.timed_out, True))
            continue
        try:
            status = int(status_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            status = 125
        timed_out = status in {124, 137}
        expected = (
            _project_path(test.expected_output_path).read_bytes()
            if test.expected_output_path is not None
            else b""
        )
        matches = outputs_equivalent(
            output_path.read_bytes(), expected, strip_leading_space=strip_leading
        )
        results.append(
            _TestResult(
                test.test_id,
                status == 0 and matches,
                timed_out,
                status != 0 and not timed_out,
            )
        )

    first_failure = next((item.test_id for item in results if not item.passed), None)
    return SuiteVerification(
        total=len(results),
        passed=sum(item.passed for item in results),
        failed=sum(not item.passed for item in results),
        timed_out=sum(item.timed_out for item in results),
        runtime_errors=sum(item.runtime_error for item in results),
        first_failure=first_failure,
    )


def verify_case(case: BenchmarkCase, config: RunnerConfig | None = None) -> CaseVerification:
    """Compile both versions and check the complete repair/validation suites."""

    active_config = config or RunnerConfig()
    defect_class = str(case.metadata.get("defect_class") or "unknown")
    try:
        docker = check_docker(active_config, PROJECT_ROOT)
        with tempfile.TemporaryDirectory(prefix="codedoctor-benchmark-") as temporary:
            root = Path(temporary)
            buggy_dir = root / "buggy"
            reference_dir = root / "reference"
            buggy_dir.mkdir()
            reference_dir.mkdir()
            buggy_compile, buggy_executable = _compile_program(
                docker, active_config, case, case.buggy, buggy_dir
            )
            reference_compile, reference_executable = _compile_program(
                docker, active_config, case, case.reference, reference_dir
            )

            if not buggy_compile.success:
                return CaseVerification(
                    case.case_id, defect_class, buggy_compile, reference_compile,
                    None, None, None, None, False, "buggy_compile_failed"
                )
            if not reference_compile.success:
                return CaseVerification(
                    case.case_id, defect_class, buggy_compile, reference_compile,
                    None, None, None, None, False, "reference_compile_failed"
                )

            reference_repair = _run_suite(
                docker, active_config, case, reference_executable,
                case.tests.repair_tests, "repair", reference_dir
            )
            reference_validation = _run_suite(
                docker, active_config, case, reference_executable,
                case.tests.validation_tests, "validation", reference_dir
            )
            if not reference_repair.success:
                reason = "reference_failed_repair_tests"
            elif not reference_validation.success:
                reason = "reference_failed_validation_tests"
            else:
                reason = None

            buggy_repair = _run_suite(
                docker, active_config, case, buggy_executable,
                case.tests.repair_tests, "repair", buggy_dir
            )
            buggy_validation = None
            if buggy_repair.success:
                buggy_validation = _run_suite(
                    docker, active_config, case, buggy_executable,
                    case.tests.validation_tests, "validation", buggy_dir
                )
            buggy_fails = not buggy_repair.success or (
                buggy_validation is not None and not buggy_validation.success
            )
            if reason is None and not buggy_fails:
                reason = "buggy_passed_all_tests"

            return CaseVerification(
                case.case_id,
                defect_class,
                buggy_compile,
                reference_compile,
                reference_repair,
                reference_validation,
                buggy_repair,
                buggy_validation,
                reason is None,
                reason,
            )
    except (DockerBackendError, OSError, ValueError, KeyError) as exc:
        detail = f"benchmark_infrastructure_error: {exc}"
        empty = _empty_compile(detail)
        return CaseVerification(
            case.case_id, defect_class, empty, empty,
            None, None, None, None, False, detail
        )
