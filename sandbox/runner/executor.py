"""Public runner API and execution backend dispatch."""

import subprocess
from pathlib import Path

from .config import RunnerConfig
from .docker_executor import DockerBackendError, execute_docker
from .local_executor import execute_local
from .models import RunnerResult, RunnerStatus


def run_cpp_program(
    source_path: str | Path,
    input_path: str | Path,
    config: RunnerConfig | None = None,
) -> RunnerResult:
    """Compile and run C++ using the configured local or Docker backend."""

    runner_config = config or RunnerConfig()
    try:
        runner_config.validate()
        source = Path(source_path).expanduser().resolve(strict=True)
        input_file = Path(input_path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"source path is not a file: {source}")
        if not input_file.is_file():
            raise ValueError(f"input path is not a file: {input_file}")

        if runner_config.backend == "local":
            return execute_local(source, input_file, runner_config)
        return execute_docker(source, input_file, runner_config)
    except (DockerBackendError, OSError, ValueError, subprocess.SubprocessError) as exc:
        return RunnerResult(
            status=RunnerStatus.INTERNAL_ERROR,
            compile=None,
            run=None,
            error=f"{type(exc).__name__}: {exc}",
        )
