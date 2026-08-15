"""Docker integration test for per-test gcov isolation and verdicts."""

import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark.config import PROJECT_ROOT
from benchmark.models import (
    BenchmarkCase,
    BenchmarkTest,
    ProblemIdentity,
    ProgramArtifact,
    TestSuites,
)
from fault_localization.collector import collect_coverage
from fault_localization.models import LocalizationInput, TestVerdict


@unittest.skipUnless(shutil.which("docker"), "Docker CLI is required")
class CoverageCollectorIntegrationTests(unittest.TestCase):
    def test_each_test_has_isolated_branch_coverage(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "benchmark") as temporary:
            directory = Path(temporary)
            source = directory / "program.c"
            source.write_text(
                "#include <stdio.h>\n"
                "int main(void) {\n"
                "    int x = 0;\n"
                "    if (scanf(\"%d\", &x) != 1) return 2;\n"
                "    if (x > 0) {\n"
                "        puts(\"positive\");\n"
                "    } else {\n"
                "        puts(\"nonpositive\");\n"
                "    }\n"
                "    if (x == 999)\n"
                "        puts(\"never\");\n"
                "    return 0;\n"
                "}\n",
                encoding="utf-8",
            )
            (directory / "Makefile").write_text(
                "FILENAME=program\n"
                "CC=gcc\n"
                "CFLAGS=-std=c99 -Wall\n"
                "LDFLAGS=-lm\n"
                "all:\n"
                "\t$(CC) $(CFLAGS) -c $(FILENAME).c -o $(FILENAME).o\n"
                "\t$(CC) $(FILENAME).o -o $(FILENAME) $(LDFLAGS)\n",
                encoding="utf-8",
            )
            (directory / "test-genprog.sh").write_text(
                "sed -e '/^$/d' -e 's/^[ \\t]*//'\n",
                encoding="utf-8",
            )
            files = {
                "pass.in": "1\n",
                "pass.out": "positive\n",
                "fail.in": "-1\n",
                "fail.out": "intentionally wrong\n",
            }
            for name, content in files.items():
                (directory / name).write_text(content, encoding="utf-8")

            relative = directory.relative_to(PROJECT_ROOT).as_posix()
            case = BenchmarkCase(
                case_id="collector-integration",
                dataset="test",
                language="c",
                problem=ProblemIdentity("0", "A"),
                buggy=ProgramArtifact(f"{relative}/program.c", "1"),
                reference=ProgramArtifact(f"{relative}/program.c", "2"),
                tests=TestSuites(
                    repair_tests=(
                        BenchmarkTest("p1", f"{relative}/pass.in", f"{relative}/pass.out"),
                        BenchmarkTest("n1", f"{relative}/fail.in", f"{relative}/fail.out"),
                    ),
                    validation_tests=(),
                ),
                metadata={"defect_class": "test", "original_dataset_path": relative},
            )
            matrix = collect_coverage(LocalizationInput.from_benchmark_case(case))

        by_id = {test.test_id: test for test in matrix.tests}
        self.assertEqual(TestVerdict.PASS, by_id["p1"].verdict)
        self.assertEqual(TestVerdict.FAIL, by_id["n1"].verdict)
        self.assertIn(6, by_id["p1"].covered_lines)
        self.assertNotIn(6, by_id["n1"].covered_lines)
        self.assertIn(8, by_id["n1"].covered_lines)
        self.assertNotIn(8, by_id["p1"].covered_lines)
        self.assertIn(11, by_id["p1"].executable_lines)
        self.assertNotIn(11, by_id["p1"].covered_lines)
        self.assertNotIn(11, by_id["n1"].covered_lines)
        pass_branches = {
            (item.line, item.branch_index): item for item in by_id["p1"].branches
        }
        fail_branches = {
            (item.line, item.branch_index): item for item in by_id["n1"].branches
        }
        self.assertTrue(pass_branches[(5, 0)].taken)
        self.assertFalse(fail_branches[(5, 0)].taken)
        self.assertFalse(pass_branches[(5, 1)].taken)
        self.assertTrue(fail_branches[(5, 1)].taken)
        self.assertIn("-std=c99 -Wall", matrix.compile_stdout)
        self.assertIn("-g -O0 --coverage", matrix.compile_stdout)

    def test_crash_dumps_partial_coverage_before_reraising_signal(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "benchmark") as temporary:
            directory = Path(temporary)
            (directory / "program.c").write_text(
                "int main(void) {\n"
                "    volatile int reached = 1;\n"
                "    int *pointer = 0;\n"
                "    if (reached) *pointer = 7;\n"
                "    return 0;\n"
                "}\n",
                encoding="utf-8",
            )
            (directory / "Makefile").write_text(
                "FILENAME=program\nCC=gcc\nCFLAGS=-std=c99\nLDFLAGS=\n"
                "all:\n"
                "\t$(CC) $(CFLAGS) -c $(FILENAME).c -o $(FILENAME).o\n"
                "\t$(CC) $(FILENAME).o -o $(FILENAME) $(LDFLAGS)\n",
                encoding="utf-8",
            )
            (directory / "test-genprog.sh").write_text("/^$/d\n", encoding="utf-8")
            (directory / "input").write_text("", encoding="utf-8")
            (directory / "output").write_text("", encoding="utf-8")
            relative = directory.relative_to(PROJECT_ROOT).as_posix()
            case = BenchmarkCase(
                case_id="collector-crash",
                dataset="test",
                language="c",
                problem=ProblemIdentity("0", "A"),
                buggy=ProgramArtifact(f"{relative}/program.c", "1"),
                reference=ProgramArtifact(f"{relative}/program.c", "2"),
                tests=TestSuites(
                    (BenchmarkTest("n1", f"{relative}/input", f"{relative}/output"),),
                    (),
                ),
                metadata={"defect_class": "test", "original_dataset_path": relative},
            )
            matrix = collect_coverage(LocalizationInput.from_benchmark_case(case))

        result = matrix.tests[0]
        self.assertEqual(TestVerdict.FAIL, result.verdict)
        self.assertEqual(139, result.exit_code)
        self.assertIn(2, result.covered_lines)
        self.assertIn(4, result.covered_lines)


if __name__ == "__main__":
    unittest.main()
