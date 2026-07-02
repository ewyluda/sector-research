"""Shared fake for AsyncSession.execute() results (no `test_` prefix so the
suite's enumeration glob skips it — same convention as model_fixtures.py)."""
from types import SimpleNamespace


class FakeResult:
    """Mimics the access patterns services use on db.execute results."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)

    def all(self):
        return self._rows
