"""Translate compiler and program process results into public models."""

from .models import CompileResult, RunnerResult, RunnerStatus, RunResult
from .process import ProcessResult


def compile_result(process: ProcessResult) -> CompileResult:
    return CompileResult(
        success=process.exit_code == 0 and not process.timed_out,
        exit_code=process.exit_code,
        stdout=process.stdout,
        stderr=process.stderr,
        time_ms=process.time_ms,
    )


def compile_failure(process: ProcessResult) -> RunnerResult | None:
    result = compile_result(process)
    if process.timed_out:
        return RunnerResult(
            status=RunnerStatus.INTERNAL_ERROR,
            compile=result,
            run=None,
            error="compilation timed out",
        )
    if process.exit_code != 0:
        return RunnerResult(
            status=RunnerStatus.COMPILE_ERROR,
            compile=result,
            run=None,
        )
    return None


def completed_result(
    compiler_process: ProcessResult, program_process: ProcessResult
) -> RunnerResult:
    run_result = RunResult(
        success=program_process.exit_code == 0 and not program_process.timed_out,
        exit_code=program_process.exit_code,
        stdout=program_process.stdout,
        stderr=program_process.stderr,
        time_ms=program_process.time_ms,
        timed_out=program_process.timed_out,
    )
    if program_process.timed_out:
        status = RunnerStatus.TIME_LIMIT_EXCEEDED
    elif program_process.exit_code != 0:
        status = RunnerStatus.RUNTIME_ERROR
    else:
        status = RunnerStatus.SUCCESS

    return RunnerResult(
        status=status,
        compile=compile_result(compiler_process),
        run=run_result,
    )
