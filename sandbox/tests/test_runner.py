"""Integration tests using the example C++ programs."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sandbox.runner import RunnerConfig, RunnerStatus, run_cpp_program
from sandbox.runner.docker_executor import _container_command
from sandbox.runner.process import ProcessResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"


class CppRunnerTests(unittest.TestCase):
    def run_example(self, name: str, timeout: float = 5.0):
        example_dir = EXAMPLES / name
        return run_cpp_program(
            example_dir / "main.cpp",
            example_dir / "input.txt",
            RunnerConfig(run_timeout_seconds=timeout),
        )

    def test_hello_world(self) -> None:
        result = self.run_example("hello_world")
        self.assertEqual(RunnerStatus.SUCCESS, result.status)
        self.assertEqual("Hello World\n", result.run.stdout)
        self.assertEqual(0, result.run.exit_code)

    def test_sum(self) -> None:
        result = self.run_example("sum")
        self.assertEqual(RunnerStatus.SUCCESS, result.status)
        self.assertEqual("3\n", result.run.stdout)

    def test_compile_error(self) -> None:
        result = self.run_example("compile_error")
        self.assertEqual(RunnerStatus.COMPILE_ERROR, result.status)
        self.assertFalse(result.compile.success)
        self.assertIsNone(result.run)
        self.assertNotEqual(0, result.compile.exit_code)
        self.assertTrue(result.compile.stderr)

    def test_runtime_error(self) -> None:
        result = self.run_example("runtime_error")
        self.assertEqual(RunnerStatus.RUNTIME_ERROR, result.status)
        self.assertTrue(result.compile.success)
        self.assertFalse(result.run.success)
        self.assertEqual(7, result.run.exit_code)
        self.assertEqual("intentional runtime failure\n", result.run.stderr)

    def test_time_limit_exceeded(self) -> None:
        result = self.run_example("timeout", timeout=0.2)
        self.assertEqual(RunnerStatus.TIME_LIMIT_EXCEEDED, result.status)
        self.assertTrue(result.run.timed_out)
        self.assertIsNone(result.run.exit_code)
        self.assertGreaterEqual(result.run.time_ms, 150)

    def test_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "sandbox.runner.main",
                str(EXAMPLES / "sum" / "main.cpp"),
                str(EXAMPLES / "sum" / "input.txt"),
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual("success", payload["status"])
        self.assertEqual("3\n", payload["run"]["stdout"])
        self.assertNotIn("analysis", payload)

    def test_missing_source_is_internal_error(self) -> None:
        result = run_cpp_program(
            EXAMPLES / "does_not_exist.cpp",
            EXAMPLES / "sum" / "input.txt",
        )
        self.assertEqual(RunnerStatus.INTERNAL_ERROR, result.status)
        self.assertIsNone(result.compile)
        self.assertIsNone(result.run)
        self.assertIn("FileNotFoundError", result.error)

    def test_local_backend_remains_available(self) -> None:
        example_dir = EXAMPLES / "sum"
        result = run_cpp_program(
            example_dir / "main.cpp",
            example_dir / "input.txt",
            RunnerConfig(backend="local"),
        )
        self.assertEqual(RunnerStatus.SUCCESS, result.status)
        self.assertEqual("3\n", result.run.stdout)


class DockerBackendTests(unittest.TestCase):
    def test_missing_docker_cli_is_internal_error(self) -> None:
        with patch("sandbox.runner.docker_executor.shutil.which", return_value=None):
            result = run_cpp_program(
                EXAMPLES / "sum" / "main.cpp",
                EXAMPLES / "sum" / "input.txt",
            )
        self.assertEqual(RunnerStatus.INTERNAL_ERROR, result.status)
        self.assertIn("Docker CLI", result.error)
        self.assertIn("not found", result.error)

    def test_unavailable_daemon_is_internal_error(self) -> None:
        failed_check = ProcessResult(1, "", "daemon unavailable", 1, False)
        with (
            patch(
                "sandbox.runner.docker_executor.shutil.which",
                return_value="/usr/bin/docker",
            ),
            patch(
                "sandbox.runner.docker_executor.run_process",
                return_value=failed_check,
            ),
        ):
            result = run_cpp_program(
                EXAMPLES / "sum" / "main.cpp",
                EXAMPLES / "sum" / "input.txt",
            )
        self.assertEqual(RunnerStatus.INTERNAL_ERROR, result.status)
        self.assertIn("Docker daemon is not available", result.error)

    def test_missing_image_is_internal_error(self) -> None:
        daemon_ok = ProcessResult(0, "27.0.0\n", "", 1, False)
        image_missing = ProcessResult(1, "", "No such image", 1, False)
        with (
            patch(
                "sandbox.runner.docker_executor.shutil.which",
                return_value="/usr/bin/docker",
            ),
            patch(
                "sandbox.runner.docker_executor.run_process",
                side_effect=[daemon_ok, image_missing],
            ),
        ):
            result = run_cpp_program(
                EXAMPLES / "sum" / "main.cpp",
                EXAMPLES / "sum" / "input.txt",
            )
        self.assertEqual(RunnerStatus.INTERNAL_ERROR, result.status)
        self.assertIn("codedoctor-cpp-sandbox", result.error)
        self.assertIn("was not found", result.error)

    def test_container_command_applies_security_limits(self) -> None:
        command = _container_command(
            "/usr/bin/docker",
            RunnerConfig(),
            Path("/tmp/codedoctor-test"),
            "codedoctor-test-container",
            ["/workspace/program"],
            interactive=True,
        )
        joined = " ".join(command)
        self.assertIn("--network none", joined)
        self.assertIn("--memory 256m", joined)
        self.assertIn("--memory-swap 256m", joined)
        self.assertIn("--cpus 1.0", joined)
        self.assertIn("--pids-limit 64", joined)
        self.assertIn("--cap-drop ALL", joined)
        self.assertIn("--security-opt no-new-privileges", joined)
        self.assertIn("--read-only", command)
        self.assertIn("--interactive", command)
        self.assertNotIn("--privileged", command)
        mount = command[command.index("--mount") + 1]
        self.assertEqual(
            "type=bind,src=/tmp/codedoctor-test,dst=/workspace",
            mount,
        )


if __name__ == "__main__":
    unittest.main()
