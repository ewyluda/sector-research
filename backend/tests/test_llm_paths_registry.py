"""Every complete_structured call site has a probe in the live smoke test
(scripts/smoke_structured_outputs.py). A new LLM path fails here until it is
added, so the per-path smoke can't silently fall behind the code."""
import ast
import os
import pathlib
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def call_sites() -> dict[str, str]:
    """{"module:schema": model expression} for each complete_structured call."""
    sites = {}
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "complete_structured":
                continue
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
            schema = kw.get("output_model") or ast.unparse(node.args[2])
            sites[f"{path.relative_to(APP)}:{schema}"] = kw.get("model", "DEEP_MODEL")
    return sites


class LLMPathRegistryTests(unittest.TestCase):
    def test_every_call_site_has_a_smoke_probe_on_its_model(self):
        from backend.app.graph.llm import DEEP_MODEL, FAST_MODEL
        from backend.scripts.smoke_structured_outputs import PATHS

        registered = {site: model for site, _schema, model in PATHS}
        found = call_sites()
        self.assertEqual(set(found), set(registered), "add the new call site to PATHS in smoke_structured_outputs.py")
        tiers = {"FAST_MODEL": FAST_MODEL, "llm.FAST_MODEL": FAST_MODEL,
                 "DEEP_MODEL": DEEP_MODEL, "llm.DEEP_MODEL": DEEP_MODEL}
        for site, expr in found.items():
            self.assertEqual(registered[site], tiers[expr], f"{site}: probe uses a different model than the code")


if __name__ == "__main__":
    unittest.main()
