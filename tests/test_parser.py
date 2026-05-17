from __future__ import annotations

import unittest

from harness.core.parser import parse_model_response


class ParserTest(unittest.TestCase):
    def test_tagged_solution_is_preferred(self):
        result = parse_model_response("<solution>\nprint(1)\n</solution>\nConfidence: high.")
        self.assertEqual("print(1)", result.artifact)
        self.assertEqual("tag", result.parse_method)
        self.assertTrue(result.has_solution_tag)
        self.assertFalse(result.parse_failed)
        self.assertEqual("high", result.confidence_label)

    def test_tagged_solution_strips_nested_code_block(self):
        result = parse_model_response("<solution>\n```python\nprint(1)\n```\n</solution>")
        self.assertEqual("print(1)", result.artifact)
        self.assertEqual("tag", result.parse_method)
        self.assertTrue(result.has_solution_tag)
        self.assertFalse(result.parse_failed)

    def test_code_block_fallback_marks_parse_failed(self):
        result = parse_model_response("```python\nprint(1)\n```\nConfidence medium.")
        self.assertEqual("print(1)", result.artifact)
        self.assertEqual("codeblock", result.parse_method)
        self.assertFalse(result.has_solution_tag)
        self.assertTrue(result.parse_failed)
        self.assertEqual("medium", result.confidence_label)

    def test_full_fallback_keeps_text_for_debugging(self):
        result = parse_model_response("plain text only")
        self.assertEqual("plain text only", result.artifact)
        self.assertEqual("full", result.parse_method)
        self.assertTrue(result.parse_failed)


if __name__ == "__main__":
    unittest.main()
