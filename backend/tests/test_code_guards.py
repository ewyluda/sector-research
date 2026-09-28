"""Repo-wide guards for bugs that were fixed once and must not come back.

(The assistant-prefill guard lives in test_llm_structured.py.)"""
import pathlib
import unittest

_APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _offenders(needle: str) -> list[str]:
    return [str(p.relative_to(_APP)) for p in _APP.rglob("*.py") if needle in p.read_text()]


class TimestampGuardTests(unittest.TestCase):
    def test_no_naive_utcnow_in_app_code(self):
        # asyncpg reads a naive datetime as LOCAL time when writing timestamptz,
        # so datetime.utcnow() stored values 4-5 hours off (verified against
        # Postgres 2026-09-27). Use datetime.now(timezone.utc).
        self.assertEqual(_offenders("utcnow("), [])


if __name__ == "__main__":
    unittest.main()
