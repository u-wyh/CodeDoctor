"""Configure and run the C++ runner in sanitizer analysis mode."""

from dataclasses import replace
from pathlib import Path

from analysis.models import AnalysisResult
from sandbox.runner.config import RunnerConfig
from sandbox.runner.executor import run_cpp_program

from .parser import SanitizerParser


SANITIZER_COMPILE_FLAGS = (
    "-g",
    "-O1",
    "-fno-omit-frame-pointer",
    "-fno-pie",
    "-no-pie",
    "-fsanitize=address,undefined",
)

SANITIZER_ENVIRONMENT = {
    "ASAN_OPTIONS": "detect_leaks=1:symbolize=1:exitcode=1",
    "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=0",
    "LSAN_OPTIONS": "symbolize=1:exitcode=1",
}


def _merge_unique(existing: tuple[str, ...], added: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*existing, *added)))


def analyze_program(
    source_path: str | Path,
    input_path: str | Path,
    config: RunnerConfig | None = None,
) -> AnalysisResult:
    """Run ASan/UBSan and parse stderr into structured bug evidence."""

    base_config = config or RunnerConfig()
    environment = dict(base_config.run_environment)
    environment.update(SANITIZER_ENVIRONMENT)
    analyzer_config = replace(
        base_config,
        extra_compile_flags=_merge_unique(
            base_config.extra_compile_flags,
            SANITIZER_COMPILE_FLAGS,
        ),
        run_environment=tuple(environment.items()),
    )
    runner_result = run_cpp_program(source_path, input_path, analyzer_config)
    report = runner_result.run.stderr if runner_result.run is not None else ""
    evidence = SanitizerParser().parse(report)
    return AnalysisResult(
        mode="sanitizer",
        runner=runner_result,
        evidence=evidence,
    )
