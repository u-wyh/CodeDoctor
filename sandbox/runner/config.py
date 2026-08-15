"""Configuration values for the C++ runner."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunnerConfig:
    """Runtime and compiler settings for one runner invocation."""

    compiler: str = "g++"
    cpp_standard: str = "c++17"
    compile_timeout_seconds: float = 20.0
    run_timeout_seconds: float = 5.0
    backend: str = "docker"
    docker_command: str = "docker"
    docker_image: str = "codedoctor-cpp-sandbox"
    extra_compile_flags: tuple[str, ...] = ()
    run_environment: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if self.compile_timeout_seconds <= 0:
            raise ValueError("compile timeout must be greater than zero")
        if self.run_timeout_seconds <= 0:
            raise ValueError("run timeout must be greater than zero")
        if self.backend not in {"local", "docker"}:
            raise ValueError("backend must be either 'local' or 'docker'")
