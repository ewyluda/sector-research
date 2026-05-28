"""Tests for step_outputs schema validation pass in _run_workspace."""
import unittest

from backend.app.services.workspace import _validate_step_outputs


class TestValidateStepOutputs(unittest.TestCase):
    def test_valid_outputs_pass_through_unchanged(self):
        outputs = {
            "update_refresh": {
                "version_before": 1,
                "version_after": 2,
                "changed_cells": [],
                "removed_cells": [],
                "new_filings": [],
                "consensus_delta": None,
                "summary": "loaded latest 10-Q",
            },
        }
        validated, had_error = _validate_step_outputs(outputs)
        self.assertFalse(had_error)
        self.assertEqual(validated["update_refresh"]["summary"], "loaded latest 10-Q")

    def test_existing_error_entry_is_preserved(self):
        """Entries with an `error` key are the existing partial-step contract and pass through."""
        outputs = {"research": {"error": "Haiku timeout"}}
        validated, had_error = _validate_step_outputs(outputs)
        self.assertTrue(had_error)
        self.assertEqual(validated["research"], {"error": "Haiku timeout"})

    def test_schema_mismatch_is_replaced_with_error_entry(self):
        """A dict that fails Pydantic validation becomes {error: ...} and flips had_error."""
        outputs = {
            "update_refresh": {
                # missing required `version_before` and `summary`
                "version_after": 2,
                "changed_cells": "this should be a list",  # wrong type
            },
        }
        validated, had_error = _validate_step_outputs(outputs)
        self.assertTrue(had_error)
        self.assertIn("error", validated["update_refresh"])
        self.assertIn("schema_validation_failed", validated["update_refresh"]["error"])

    def test_unknown_step_name_is_passed_through_untouched(self):
        """Defensive: if a new step name appears that has no registered schema, don't break."""
        outputs = {"future_step": {"hello": "world"}}
        validated, had_error = _validate_step_outputs(outputs)
        self.assertFalse(had_error)
        self.assertEqual(validated["future_step"], {"hello": "world"})


if __name__ == "__main__":
    unittest.main()
