import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.api import questions


class QuestionsApiFilterTests(unittest.TestCase):
    def test_all_status_normalizes_to_unfiltered(self) -> None:
        self.assertIsNone(questions._normalize_status_filter("all"))

    def test_missing_status_keeps_default_open(self) -> None:
        self.assertEqual(questions._normalize_status_filter(None), "open")


if __name__ == "__main__":
    unittest.main()
