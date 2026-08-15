"""Unit tests for BenchmarkCase and Codeflaws layout conversion."""

import json
import tempfile
import unittest
from pathlib import Path

from benchmark.codeflaws import parse_case_directory
from benchmark.config import PROJECT_ROOT
from benchmark.models import BenchmarkCase


class BenchmarkModelTests(unittest.TestCase):
    def test_reference_requires_explicit_evaluation_access(self) -> None:
        value = {
            "case_id": "sample",
            "dataset": "codeflaws",
            "language": "c",
            "problem": {"contest_id": "1", "problem_id": "A"},
            "buggy": {"source_path": "bug.c", "submission_id": "10"},
            "reference": {"source_path": "ref.c", "submission_id": "11"},
            "tests": {"repair_tests": [], "validation_tests": []},
            "metadata": {"defect_class": "DCCR"},
        }
        case = BenchmarkCase.from_dict(value)
        with self.assertRaises(PermissionError):
            case.get_reference_source()
        self.assertNotIn("reference", case.repair_time_view())

    def test_manifest_model_round_trip(self) -> None:
        value = {
            "case_id": "1-A-bug-10-11",
            "dataset": "codeflaws",
            "language": "c",
            "problem": {"contest_id": "1", "problem_id": "A"},
            "buggy": {"source_path": "bug.c", "submission_id": "10"},
            "reference": {"source_path": "ref.c", "submission_id": "11"},
            "tests": {
                "repair_tests": [
                    {
                        "test_id": "1",
                        "input_path": "input1",
                        "expected_output_path": "output1",
                    }
                ],
                "validation_tests": [],
            },
            "metadata": {"defect_class": "DCCR"},
        }
        case = BenchmarkCase.from_dict(json.loads(json.dumps(value)))
        self.assertEqual(value, case.to_dict())

    def test_codeflaws_layout_conversion_uses_script_mappings(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "benchmark") as temp:
            case_directory = Path(temp) / "1-A-bug-10-11"
            case_directory.mkdir()
            for name in (
                "1-A-10.c",
                "1-A-11.c",
                "Makefile",
                "input-pos1",
                "output-pos1",
                "input-neg1",
                "heldout-input-pos1",
                "heldout-output-pos1",
            ):
                (case_directory / name).write_text("sample\n", encoding="utf-8")

            (case_directory / "test-genprog.sh").write_text(
                'case $1 in\n'
                'p1) run_test "$INPUT_NAME"1 "$OUTPUT_NAME"1 ;;\n'
                'n1) run_test "$NEGINPUT_NAME"1 "$NEGOUTPUT_NAME"1 ;;\n'
                "esac\n",
                encoding="utf-8",
            )
            (case_directory / "test-valid.sh").write_text(
                'case $1 in\n'
                'p1) run_test "$INPUT_NAME"1 "$OUTPUT_NAME"1 ;;\n'
                "esac\n",
                encoding="utf-8",
            )

            case = parse_case_directory(
                case_directory,
                {
                    case_directory.name: {
                        "defect_class": "DCCR",
                        "error_type": "WRONG_ANSWER",
                        "error_code": "-",
                    }
                },
            )

        self.assertEqual("1", case.problem.contest_id)
        self.assertEqual("A", case.problem.problem_id)
        self.assertEqual("DCCR", case.metadata["defect_class"])
        self.assertEqual(2, len(case.tests.repair_tests))
        unmatched = next(
            test for test in case.tests.repair_tests if test.test_id == "n1"
        )
        self.assertTrue(unmatched.expected_output_path.endswith("output-neg1"))


if __name__ == "__main__":
    unittest.main()
