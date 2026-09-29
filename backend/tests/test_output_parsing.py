"""Characterization tests for output_parser.parse_structured_output edges (M0.3).

The score-inventing _extract_score / _extract_key_findings fallbacks were removed
2026-09-26 along with their tests (app code now uses complete_structured).
"""
import unittest

from pydantic import BaseModel

from backend.app.graph.output_parser import parse_structured_output


class _ToySchema(BaseModel):
    name: str
    score: int


class TestParseStructuredOutputEdges(unittest.TestCase):
    def test_clean_json(self):
        parsed, err = parse_structured_output('{"name": "NVDA", "score": 9}', _ToySchema)
        self.assertIsNone(err)
        self.assertEqual(parsed.name, "NVDA")

    def test_markdown_fenced_json(self):
        raw = '```json\n{"name": "NVDA", "score": 9}\n```'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(err)
        self.assertEqual(parsed.score, 9)

    def test_prose_preamble(self):
        raw = 'Here is the result you asked for:\n{"name": "NVDA", "score": 9}'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(err)

    def test_empty_response(self):
        parsed, err = parse_structured_output("", _ToySchema)
        self.assertIsNone(parsed)
        self.assertEqual(err, "empty response")

    def test_bare_array_recovery_behavior(self):
        # CHARACTERIZATION: a top-level JSON array wrapping a valid object.
        # The greedy \{.*\} regex finds the inner {"name": "NVDA", "score": 9}
        # and parses it successfully — the surrounding array brackets are ignored.
        parsed, err = parse_structured_output('[{"name": "NVDA", "score": 9}]', _ToySchema)
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.name, "NVDA")
        self.assertEqual(parsed.score, 9)

    def test_two_json_objects_fail_with_decode_error(self):
        # CHARACTERIZATION: greedy regex spans first { to last } across both
        # objects, producing invalid JSON -> JSONDecodeError: Extra data.
        raw = '{"name": "A", "score": 1}\n{"name": "B", "score": 2}'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(parsed)
        self.assertIn("JSONDecodeError", err or "")

    def test_validation_error_is_returned_not_raised(self):
        parsed, err = parse_structured_output('{"name": "NVDA"}', _ToySchema)
        self.assertIsNone(parsed)
        self.assertIn("ValidationError", err or "")

    def test_never_raises_on_garbage(self):
        parsed, err = parse_structured_output("}{ not json at all }{", _ToySchema)
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
