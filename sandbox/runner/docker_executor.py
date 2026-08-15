"""Docker-based C++ compilation and execution backend."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from .config import RunnerConfig
from .models import RunnerResult
from .process import ProcessResult, run_process
from .result_factory import compile_failure, completed_result


class DockerBackendError(RuntimeError):
    """Raised when Docker infrastructure cannot execute a submission."""


def _error_detail(process: ProcessResult) -> str:
    return (process.stderr or process.stdout).strip() or "no details available"


def check_docker(config: RunnerConfig, cwd: Path) -> str:
    """Return the Docker CLI path after checking daemon and image availability."""

    docker = shutil.which(config.docker_command)
    if docker is None:
        raise DockerBackendError(
            f"Docker CLI '{config.docker_command}' was not found in PATH"
        )

    daemon = run_process(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        timeout_seconds=5.0,
        cwd=cwd,
    )
    if daemon.timed_out:
        raise DockerBackendError("Docker daemon check timed out")
    if daemon.exit_code != 0:
        raise DockerBackendError(
            f"Docker daemon is not available: {_error_detail(daemon)}"
        )

    image = run_process(
        [docker, "image", "inspect", config.docker_image],
        timeout_seconds=5.0,
        cwd=cwd,
    )
    if image.timed_out:
        raise DockerBackendError("Docker image check timed out")
    if image.exit_code != 0:
        raise DockerBackendError(
            f"Docker image '{config.docker_image}' was not found; "
            "build it from sandbox/docker/Dockerfile"
        )
    return docker


def _container_command(
    docker: str,
    config: RunnerConfig,
    work_dir: Path,
    container_name: str,
    command: list[str],
    *,
    interactive: bool,
    environment: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    docker_command = [
        docker,
        "run",
        "--name",
        container_name,
        "--network",
        "none",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--cpus",
        "1.0",
        "--pids-limit",
        "64",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--ulimit",
        "nofile=256:256",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--workdir",
        "/workspace",
        "--mount",
        f"type=bind,src={work_dir},dst=/workspace",
    ]
    for name, value in environment:
        docker_command.extend(("--env", f"{name}={value}"))
    if interactive:
        docker_command.append("--interactive")
    return [*docker_command, config.docker_image, *command]


def _remove_container(docker: str, container_name: str, cwd: Path) -> None:
    cleanup = run_process(
        [docker, "rm", "--force", container_name],
        timeout_seconds=10.0,
        cwd=cwd,
    )
    if cleanup.timed_out:
        raise DockerBackendError(
            f"timed out while removing Docker container '{container_name}'"
        )
    if cleanup.exit_code != 0 and "No such container" not in cleanup.stderr:
        raise DockerBackendError(
            f"failed to remove Docker container '{container_name}': "
            f"{_error_detail(cleanup)}"
        )


def run_container(
    docker: str,
    config: RunnerConfig,
    work_dir: Path,
    command: list[str],
    timeout_seconds: float,
    *,
    stdin_file: Path | None = None,
    environment: tuple[tuple[str, str], ...] = (),
) -> ProcessResult:
    """Run one command with the CodeDoctor Docker security constraints."""

    container_name = f"codedoctor-{uuid.uuid4().hex}"
    docker_command = _container_command(
        docker,
        config,
        work_dir,
        container_name,
        command,
        interactive=stdin_file is not None,
        environment=environment,
    )
    try:
        if stdin_file is None:
            result = run_process(
                docker_command,
                timeout_seconds=timeout_seconds,
                cwd=work_dir,
            )
        else:
            with stdin_file.open("rb") as stdin:
                result = run_process(
                    docker_command,
                    timeout_seconds=timeout_seconds,
                    cwd=work_dir,
                    stdin_file=stdin,
                )

        if result.exit_code == 125:
            inspect = run_process(
                [docker, "inspect", container_name],
                timeout_seconds=5.0,
                cwd=work_dir,
            )
            if inspect.exit_code != 0:
                raise DockerBackendError(
                    f"Docker failed to start the sandbox container: "
                    f"{_error_detail(result)}"
                )
        return result
    finally:
        _remove_container(docker, container_name, work_dir)


def execute_docker(
    source: Path, input_file: Path, config: RunnerConfig
) -> RunnerResult:
    """Compile and run in separate constrained Docker containers."""

    docker = check_docker(config, source.parent)
    with tempfile.TemporaryDirectory(prefix="codedoctor-docker-") as temp_dir:
        work_dir = Path(temp_dir).resolve()
        container_source = work_dir / "main.cpp"
        container_input = work_dir / "input.txt"
        shutil.copyfile(source, container_source)
        shutil.copyfile(input_file, container_input)

        compiler_process = run_container(
            docker,
            config,
            work_dir,
            [
                config.compiler,
                f"-std={config.cpp_standard}",
                *config.extra_compile_flags,
                "/workspace/main.cpp",
                "-o",
                "/workspace/program",
            ],
            config.compile_timeout_seconds,
        )
        failure = compile_failure(compiler_process)
        if failure is not None:
            return failure

        program_process = run_container(
            docker,
            config,
            work_dir,
            ["/workspace/program"],
            config.run_timeout_seconds,
            stdin_file=container_input,
            environment=config.run_environment,
        )
        return completed_result(compiler_process, program_process)
