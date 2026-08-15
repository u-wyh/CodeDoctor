"""Original host-based C++ execution backend."""

import os
import tempfile
from pathlib import Path

from .config import RunnerConfig
from .models import RunnerResult
from .process import run_process
from .result_factory import compile_failure, completed_result


def execute_local(
    source: Path, input_file: Path, config: RunnerConfig
) -> RunnerResult:
    """Compile and run directly on the host Linux system."""

    with tempfile.TemporaryDirectory(prefix="codedoctor-local-") as temp_dir:
        work_dir = Path(temp_dir)
        executable = work_dir / "program"
        compiler_process = run_process(
            [
                config.compiler,
                f"-std={config.cpp_standard}",
                *config.extra_compile_flags,
                str(source),
                "-o",
                str(executable),
            ],
            timeout_seconds=config.compile_timeout_seconds,
            cwd=work_dir,
        )
        failure = compile_failure(compiler_process)
        if failure is not None:
            return failure

        with input_file.open("rb") as stdin:
            program_process = run_process(
                [str(executable)],
                timeout_seconds=config.run_timeout_seconds,
                cwd=work_dir,
                stdin_file=stdin,
                environment={**os.environ, **dict(config.run_environment)},
            )
        return completed_result(compiler_process, program_process)
