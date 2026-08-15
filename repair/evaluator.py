"""Compile and test generated source in the existing constrained Docker sandbox."""

import shutil
import tempfile
from pathlib import Path

from benchmark.config import (
    BENCHMARK_COMPILE_TIMEOUT_SECONDS,
    BENCHMARK_RUN_TIMEOUT_SECONDS,
    PROJECT_ROOT,
)
from benchmark.execution import outputs_equivalent, script_strips_leading_space
from benchmark.models import BenchmarkCase, BenchmarkTest
from sandbox.runner.config import RunnerConfig
from sandbox.runner.docker_executor import check_docker, run_container

from .models import (
    PatchClassification,
    PatchEvaluation,
    RepairTestEvidence,
    TestResult,
)


def classify_patch_results(
    compile_success: bool,
    repair_tests: tuple[TestResult, ...],
    validation_tests: tuple[TestResult, ...],
) -> tuple[bool, bool, PatchClassification, tuple[str, ...]]:
    if not compile_success:
        return False, False, PatchClassification.COMPILE_ERROR, ("compile_error",)
    plausible = bool(repair_tests) and all(item.passed for item in repair_tests)
    validated = plausible and bool(validation_tests) and all(
        item.passed for item in validation_tests
    )
    if not plausible:
        return (
            False,
            False,
            PatchClassification.REPAIR_TEST_FAILED,
            ("repair_test_failed",),
        )
    if validated:
        return True, True, PatchClassification.VALIDATED_PATCH, ()
    return (
        True,
        False,
        PatchClassification.PLAUSIBLE_PATCH,
        ("validation_overfitting",),
    )


def _project_path(relative: str) -> Path:
    path = (PROJECT_ROOT / relative).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError(f"benchmark path escapes project root: {relative}")
    return path


def _run_test(
    docker: str,
    config: RunnerConfig,
    case: BenchmarkCase,
    executable: Path,
    test: BenchmarkTest,
    suite: str,
    root: Path,
    index: int,
) -> TestResult:
    work = root / f"{suite}-{index:04d}"
    work.mkdir()
    shutil.copy2(executable, work / "program")
    input_path = work / "input.txt"
    if test.input_path is not None:
        shutil.copyfile(_project_path(test.input_path), input_path)
    else:
        input_path.write_bytes(b"")
    process = run_container(
        docker,
        config,
        work,
        ["/workspace/program"],
        BENCHMARK_RUN_TIMEOUT_SECONDS,
        stdin_file=input_path,
    )
    expected = (
        _project_path(test.expected_output_path).read_bytes()
        if test.expected_output_path is not None
        else b""
    )
    actual = process.stdout.encode("utf-8", errors="replace")
    passed = process.exit_code == 0 and outputs_equivalent(
        actual,
        expected,
        strip_leading_space=script_strips_leading_space(case, suite),
    )
    return TestResult(
        test_id=test.test_id,
        passed=passed,
        stdout=process.stdout,
        stderr=process.stderr,
        exit_code=process.exit_code,
        timed_out=process.timed_out,
    )


def evaluate_source(
    case: BenchmarkCase,
    source: str,
    *,
    include_validation: bool = True,
    config: RunnerConfig | None = None,
) -> PatchEvaluation:
    active = config or RunnerConfig()
    docker = check_docker(active, PROJECT_ROOT)
    original_source = _project_path(case.buggy.source_path)
    makefile = _project_path(str(case.metadata["makefile_path"]))
    with tempfile.TemporaryDirectory(prefix="codedoctor-repair-eval-") as temporary:
        root = Path(temporary)
        compile_dir = root / "compile"
        compile_dir.mkdir()
        source_path = compile_dir / original_source.name
        source_path.write_text(source, encoding="utf-8")
        shutil.copy2(makefile, compile_dir / "Makefile")
        compiled = run_container(
            docker,
            active,
            compile_dir,
            ["make", "--no-print-directory", f"FILENAME={source_path.stem}"],
            BENCHMARK_COMPILE_TIMEOUT_SECONDS,
        )
        if compiled.timed_out or compiled.exit_code != 0:
            return PatchEvaluation(
                False,
                compiled.stdout,
                compiled.stderr,
                compiled.exit_code,
                (),
                (),
                False,
                False,
                PatchClassification.COMPILE_ERROR,
                ("compile_error",),
            )
        executable = compile_dir / source_path.stem
        repair = tuple(
            _run_test(
                docker, active, case, executable, test, "repair", root, index
            )
            for index, test in enumerate(case.tests.repair_tests)
        )
        plausible = bool(repair) and all(item.passed for item in repair)
        validation = ()
        if plausible and include_validation:
            validation = tuple(
                _run_test(
                    docker,
                    active,
                    case,
                    executable,
                    test,
                    "validation",
                    root,
                    index,
                )
                for index, test in enumerate(case.tests.validation_tests)
            )
        plausible, validated, classification, modes = classify_patch_results(
            True, repair, validation
        )
        return PatchEvaluation(
            True,
            compiled.stdout,
            compiled.stderr,
            compiled.exit_code,
            repair,
            validation,
            plausible,
            validated,
            classification,
            modes,
        )


def repair_execution_evidence(
    case: BenchmarkCase, evaluation: PatchEvaluation
) -> tuple[RepairTestEvidence, ...]:
    by_id = {item.test_id: item for item in evaluation.repair_tests}
    evidence = []
    for test in case.tests.repair_tests:
        result = by_id[test.test_id]
        evidence.append(
            RepairTestEvidence(
                test_id=test.test_id,
                verdict="PASS" if result.passed else "FAIL",
                actual_stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                timed_out=result.timed_out,
            )
        )
    return tuple(evidence)
