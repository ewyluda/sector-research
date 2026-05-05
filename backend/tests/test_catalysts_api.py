import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.api import catalysts


class CatalystListQueryTests(unittest.TestCase):
    def test_latest_query_excludes_json_null_thesis_structured_values(self) -> None:
        sql, params = catalysts._build_list_catalysts_sql(ticker=None, run_id=None)

        self.assertIn(
            "jsonb_typeof(state->'phase_outputs'->'thesis'->'structured') = 'object'",
            sql,
        )
        self.assertNotIn(
            "state->'phase_outputs'->'thesis'->'structured' IS NOT NULL",
            sql,
        )
        self.assertEqual(params, {})

    def test_run_id_query_scopes_to_viewed_run_without_latest_cte(self) -> None:
        sql, params = catalysts._build_list_catalysts_sql(
            ticker=None,
            run_id="run-123",
        )

        self.assertNotIn("WITH latest", sql)
        self.assertIn("WHERE c.run_id = :run_id", sql)
        self.assertEqual(params, {"run_id": "run-123"})


if __name__ == "__main__":
    unittest.main()
