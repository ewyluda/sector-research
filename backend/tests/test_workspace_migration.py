import unittest
from pathlib import Path


class TestWorkspaceMigration(unittest.TestCase):
    def test_running_workspace_run_is_unique_per_ticker(self):
        migration = Path(
            "backend/migrations/versions/28aa0887373a_workspace_runs_table.py"
        ).read_text()

        self.assertIn("uq_workspace_runs_one_running_per_ticker", migration)
        self.assertIn("unique=True", migration)
        self.assertIn("status = 'running'", migration)


if __name__ == "__main__":
    unittest.main()
