"""Per-test gcov collection in isolated CodeDoctor Docker containers."""

import shutil
import tempfile
from pathlib import Path

from benchmark.config import (
    BENCHMARK_COMPILE_TIMEOUT_SECONDS,
    BENCHMARK_RUN_TIMEOUT_SECONDS,
    PROJECT_ROOT,
)
from benchmark.execution import outputs_equivalent
from sandbox.runner.config import RunnerConfig
from sandbox.runner.docker_executor import check_docker, run_container

from .gcov_parser import parse_gcov_json
from .models import CoverageMatrix, LocalizationInput, TestCoverage, TestVerdict


class CoverageCollectionError(RuntimeError):
    """Raised when compilation or gcov collection cannot produce a matrix."""


GCOV_SIGNAL_HEADER = r"""#ifndef CODEDOCTOR_GCOV_SIGNAL_H
#define CODEDOCTOR_GCOV_SIGNAL_H
#include <signal.h>
#include <stdlib.h>
extern void __gcov_dump(void);
static volatile sig_atomic_t codedoctor_gcov_dumping = 0;
static void codedoctor_gcov_signal_handler(int signal_number) {
    if (!codedoctor_gcov_dumping) {
        codedoctor_gcov_dumping = 1;
        __gcov_dump();
    }
    signal(signal_number, SIG_DFL);
    raise(signal_number);
    _Exit(128 + signal_number);
}
__attribute__((constructor))
static void codedoctor_install_gcov_signal_handlers(void) {
    signal(SIGSEGV, codedoctor_gcov_signal_handler);
    signal(SIGABRT, codedoctor_gcov_signal_handler);
    signal(SIGFPE, codedoctor_gcov_signal_handler);
    signal(SIGBUS, codedoctor_gcov_signal_handler);
    signal(SIGILL, codedoctor_gcov_signal_handler);
}
#endif
"""
COVERAGE_COMPILER_COMMAND = (
    "gcc -g -O0 --coverage "
    "-include /workspace/codedoctor_gcov_signal.h"
)


def _project_path(relative_path: str) -> Path:
    path = (PROJECT_ROOT / relative_path).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise CoverageCollectionError(
            f"benchmark path escapes project root: {relative_path}"
        )
    return path


def _strips_leading_space(localization_input: LocalizationInput) -> bool:
    original = _project_path(
        str(localization_input.metadata["original_dataset_path"])
    )
    script = (original / "test-genprog.sh").read_text(
        encoding="utf-8", errors="replace"
    )
    return "s/^[ " in script


def _read_status(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def collect_coverage(
    localization_input: LocalizationInput,
    config: RunnerConfig | None = None,
) -> CoverageMatrix:
    """Compile once, then run every repair test in a fresh workspace/container."""

    active_config = config or RunnerConfig()
    source = _project_path(localization_input.buggy_source_path)
    original = _project_path(
        str(localization_input.metadata["original_dataset_path"])
    )
    makefile = original / "Makefile"
    docker = check_docker(active_config, PROJECT_ROOT)
    signal_header_name = "codedoctor_gcov_signal.h"
    compiler = COVERAGE_COMPILER_COMMAND
    compile_command = (
        "make",
        "--no-print-directory",
        f"FILENAME={source.stem}",
        f"CC={compiler}",
    )

    with tempfile.TemporaryDirectory(
        prefix="codedoctor-coverage-"
    ) as temporary:
        root = Path(temporary)
        compile_dir = root / "compile"
        compile_dir.mkdir()
        shutil.copy2(source, compile_dir / source.name)
        shutil.copy2(makefile, compile_dir / "Makefile")
        (compile_dir / signal_header_name).write_text(
            GCOV_SIGNAL_HEADER, encoding="ascii"
        )
        compiled = run_container(
            docker,
            active_config,
            compile_dir,
            list(compile_command),
            BENCHMARK_COMPILE_TIMEOUT_SECONDS,
        )
        if compiled.timed_out or compiled.exit_code != 0:
            detail = (compiled.stderr or compiled.stdout).strip()
            raise CoverageCollectionError(
                f"coverage compilation failed for {localization_input.case_id}: "
                f"{detail or 'no compiler output'}"
            )

        executable = compile_dir / source.stem
        gcno = compile_dir / f"{source.stem}.gcno"
        if not executable.is_file() or not gcno.is_file():
            raise CoverageCollectionError(
                f"coverage compilation did not produce executable/gcno for "
                f"{localization_input.case_id}"
            )

        strip_leading = _strips_leading_space(localization_input)
        test_results = []
        for index, test in enumerate(localization_input.repair_tests):
            if test.input_path is None or test.expected_output_path is None:
                raise CoverageCollectionError(
                    f"repair test {test.test_id} is incomplete"
                )
            test_dir = root / f"test-{index:04d}"
            test_dir.mkdir()
            for artifact in (
                source,
                executable,
                gcno,
                compile_dir / signal_header_name,
            ):
                shutil.copy2(artifact, test_dir / artifact.name)
            input_path = test_dir / "input.txt"
            shutil.copyfile(_project_path(test.input_path), input_path)

            script = (
                f"timeout -k 1s {BENCHMARK_RUN_TIMEOUT_SECONDS}s "
                f"./{source.stem} < input.txt > actual.out 2> program.err; "
                'printf "%s\\n" "$?" > program.status; '
                "gcov --json-format --branch-probabilities --branch-counts "
                f"{source.name} > gcov.out 2> gcov.err; "
                'printf "%s\\n" "$?" > gcov.status; exit 0'
            )
            run = run_container(
                docker,
                active_config,
                test_dir,
                ["/bin/sh", "-c", script],
                BENCHMARK_RUN_TIMEOUT_SECONDS + 8.0,
            )
            status = _read_status(test_dir / "program.status")
            gcov_status = _read_status(test_dir / "gcov.status")
            if run.timed_out or gcov_status != 0:
                detail_path = test_dir / "gcov.err"
                detail = (
                    detail_path.read_text(encoding="utf-8", errors="replace")
                    if detail_path.exists()
                    else run.stderr
                )
                raise CoverageCollectionError(
                    f"gcov failed for {localization_input.case_id}/{test.test_id}: "
                    f"{detail.strip() or 'no details'}"
                )
            gcov_files = list(test_dir.glob("*.gcov.json.gz"))
            if len(gcov_files) != 1:
                raise CoverageCollectionError(
                    f"expected one gcov JSON for {localization_input.case_id}/"
                    f"{test.test_id}, found {len(gcov_files)}"
                )
            coverage = parse_gcov_json(
                gcov_files[0], source.name
            )
            actual = (test_dir / "actual.out").read_bytes()
            expected = _project_path(test.expected_output_path).read_bytes()
            timed_out = status in {124, 137} or run.timed_out
            passed = (
                status == 0
                and outputs_equivalent(
                    actual,
                    expected,
                    strip_leading_space=strip_leading,
                )
            )
            test_results.append(
                TestCoverage(
                    test_id=test.test_id,
                    verdict=(TestVerdict.PASS if passed else TestVerdict.FAIL),
                    covered_lines=coverage.covered_lines,
                    executable_lines=coverage.executable_lines,
                    exit_code=status,
                    timed_out=timed_out,
                    gcov_version=coverage.gcc_version,
                    branches=coverage.branches,
                )
            )

        return CoverageMatrix(
            case_id=localization_input.case_id,
            source_path=localization_input.buggy_source_path,
            compile_command=compile_command,
            compile_stdout=compiled.stdout,
            compile_stderr=compiled.stderr,
            tests=tuple(test_results),
        )
