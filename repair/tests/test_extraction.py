"""Patch extraction tests."""

import unittest

from repair.extraction import extract_source


SOURCE = "#include <stdio.h>\nint main(){return 0;}"


class ExtractionTests(unittest.TestCase):
    def test_cpp_fenced_block(self) -> None:
        result = extract_source(f"```cpp\n{SOURCE}\n```")
        self.assertEqual("success", result.status)
        self.assertEqual("fenced_code", result.strategy)

    def test_c_fenced_block(self) -> None:
        self.assertEqual(
            "success", extract_source(f"```c\n{SOURCE}\n```").status
        )

    def test_plain_source(self) -> None:
        result = extract_source(SOURCE)
        self.assertEqual("plain_source", result.strategy)

    def test_invalid_response(self) -> None:
        self.assertEqual(
            "invalid_model_output", extract_source("I cannot repair this.").status
        )

    def test_extra_explanation_and_code(self) -> None:
        result = extract_source(f"Here is the patch:\n```cpp\n{SOURCE}\n```\nDone")
        self.assertEqual("success", result.status)
        self.assertNotIn("Here is", result.source)


if __name__ == "__main__":
    unittest.main()
