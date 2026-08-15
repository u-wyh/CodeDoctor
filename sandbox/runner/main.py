"""Command-line entry point for the CodeDoctor C++ runner."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from sandbox.runner.config import RunnerConfig
    from sandbox.runner.executor import run_cpp_program
else:
    from .config import RunnerConfig
    from .executor import run_cpp_program


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile and run a C++17 source file with file-based stdin."
    )
    parser.add_argument("source", help="path to main.cpp")
    parser.add_argument("input", help="path to input.txt")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="program timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "--compile-timeout",
        type=float,
        default=20.0,
        help="compiler timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--backend",
        choices=("docker", "local"),
        default="docker",
        help="execution backend (default: docker)",
    )
    parser.add_argument(
        "--docker-image",
        default="codedoctor-cpp-sandbox",
        help="Docker image used by the docker backend",
    )
    parser.add_argument(
        "--analysis",
        choices=("sanitizer",),
        help="run an optional dynamic analysis mode",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config = RunnerConfig(
        run_timeout_seconds=args.timeout,
        compile_timeout_seconds=args.compile_timeout,
        backend=args.backend,
        docker_image=args.docker_image,
    )
    if args.analysis == "sanitizer":
        from analysis.sanitizer.analyzer import analyze_program

        result = analyze_program(args.source, args.input, config)
    else:
        result = run_cpp_program(args.source, args.input, config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
