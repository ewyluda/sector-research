"""Characterization tests pinning nodes.py parsing helpers and output_parser edges (M0.3).

These document CURRENT behavior (including the _extract_score silent-50 fallback)
ahead of the planned nodes.py split. If one fails, the helper changed — that's the signal.
"""
import unittest

from pydantic import BaseModel

from backend.app.graph.nodes import _extract_key_findings, _extract_score
from backend.app.graph.output_parser import parse_structured_output


class _ToySchema(BaseModel):
    name: str
    score: int


class TestExtractScore(unittest.TestCase):
    def test_score_label(self):
        self.assertEqual(_extract_score("blah\nSCORE: 85/100\nblah"), 85)

    def test_conviction_label(self):
        self.assertEqual(_extract_score("CONVICTION: 42/100"), 42)

    def test_case_insensitive(self):
        self.assertEqual(_extract_score("score: 61/100"), 61)

    def test_bare_fraction_fallback(self):
        self.assertEqual(_extract_score("I rate this 73/100 overall."), 73)

    def test_labeled_wins_over_bare(self):
        # First pattern (labeled) is tried before the bare fallback.
        self.assertEqual(_extract_score("3/100 chance... SCORE: 90/100"), 90)

    def test_clamps_above_100(self):
        self.assertEqual(_extract_score("SCORE: 150/100"), 100)

    def test_silent_50_fallback_when_absent(self):
        # CHARACTERIZATION: no score anywhere -> silently 50, not an error.
        self.assertEqual(_extract_score("no numeric verdict here"), 50)

    def test_silent_50_on_empty(self):
        self.assertEqual(_extract_score(""), 50)

    def test_space_before_slash_defeats_both_patterns(self):
        # CHARACTERIZATION: "85 /100" matches neither pattern -> silent 50.
        self.assertEqual(_extract_score("SCORE: 85 /100"), 50)

    def test_negative_score_falls_through_to_bare_pattern(self):
        # CHARACTERIZATION: labeled pattern rejects the minus; bare fallback grabs "5/100".
        self.assertEqual(_extract_score("SCORE: -5/100"), 5)


class TestExtractKeyFindings(unittest.TestCase):
    def test_collects_bullets_after_heading(self):
        text = (
            "Analysis...\n"
            "Key findings:\n"
            "- Revenue acceleration is broad-based\n"
            "* Margins expanded for the 4th quarter\n"
            "3. Management guided above consensus\n"
        )
        self.assertEqual(_extract_key_findings(text), [
            "Revenue acceleration is broad-based",
            "Margins expanded for the 4th quarter",
            "Management guided above consensus",
        ])

    def test_caps_at_five(self):
        bullets = "\n".join(f"- finding number {i} is long enough" for i in range(8))
        text = f"Key findings:\n{bullets}"
        self.assertEqual(len(_extract_key_findings(text)), 5)

    def test_stops_at_blank_line_after_findings(self):
        text = (
            "Key findings:\n"
            "- the only finding worth keeping\n"
            "\n"
            "- this is after the blank line section break\n"
        )
        self.assertEqual(_extract_key_findings(text), ["the only finding worth keeping"])

    def test_skips_short_lines(self):
        text = "Key findings:\n- tiny\n- a genuinely substantive finding\n"
        self.assertEqual(_extract_key_findings(text), ["a genuinely substantive finding"])

    def test_no_heading_returns_empty(self):
        self.assertEqual(_extract_key_findings("- bullet without a heading above it"), [])

    def test_digit_leading_bullets_are_mangled(self):
        # CHARACTERIZATION: lstrip("•-*123456789. ") eats leading digits of the
        # finding itself ("2024..." -> "024...") — known quirk, documented not endorsed.
        self.assertEqual(
            _extract_key_findings("Key findings:\n- 2024 revenue grew strongly"),
            ["024 revenue grew strongly"],
        )


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
