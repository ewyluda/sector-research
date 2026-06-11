"""Tests for prospectus_categories.run_categories."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.services.prospectus_categories import run_categories
from backend.app.models.prospectus_schemas import CategoriesStepOutput


def _category_payload(name: str, score: int = 65) -> str:
    return json.dumps({
        "category": name,
        "content": f"## Analysis for {name}\n\nThis is markdown.",
        "score": score,
        "key_findings": [f"{name} finding 1", f"{name} finding 2"],
    })


class TestRunCategories(unittest.IsolatedAsyncioTestCase):
    async def test_all_seven_categories_run(self):
        async def fake_complete(*, system, user, **kw):
            # Extract category name from system prompt
            for cat in (
                "Business Quality", "Risk Assessment", "Growth & Earnings",
                "Management & Governance", "Future Durability",
                "Macro & Regime", "IPO Mechanics",
            ):
                if cat in system:
                    return _category_payload(cat)
            return _category_payload("UNKNOWN")

        with patch("backend.app.services.prospectus_categories.complete",
                   new=AsyncMock(side_effect=fake_complete)):
            out = await run_categories(
                issuer_name="ACME Rockets",
                filing_date="2026-05-20",
                form_type="S-1",
                sections_text={
                    "s1_business": "We build rockets.",
                    "s1_risk_factors": "Risks include unicorn attacks.",
                    "s1_mda": "Revenues grew.",
                    "s1_principal_stockholders": "Founder owns 78%.",
                    "s1_use_of_proceeds": "GP&A.",
                    "s1_capitalization": "Debt is low.",
                    "s1_dilution": "20% dilution.",
                    "s1_underwriting": "Goldman / MS / JPM.",
                },
                counterparty_context="",
                macro_indicators="",
            )

        self.assertIsInstance(out, CategoriesStepOutput)
        self.assertEqual(set(out.results.keys()), {
            "Business Quality", "Risk Assessment", "Growth & Earnings",
            "Management & Governance", "Future Durability",
            "Macro & Regime", "IPO Mechanics",
        })
        self.assertEqual(out.failures, {})

    async def test_one_category_failure_does_not_abort_others(self):
        async def fake_complete(*, system, user, **kw):
            if "Business Quality" in system:
                raise RuntimeError("anthropic 503")
            for cat in (
                "Risk Assessment", "Growth & Earnings",
                "Management & Governance", "Future Durability",
                "Macro & Regime", "IPO Mechanics",
            ):
                if cat in system:
                    return _category_payload(cat)
            return _category_payload("?")

        with patch("backend.app.services.prospectus_categories.complete",
                   new=AsyncMock(side_effect=fake_complete)):
            out = await run_categories(
                issuer_name="X", filing_date="2026-05-20", form_type="S-1",
                sections_text={k: "x" for k in (
                    "s1_business", "s1_risk_factors", "s1_mda",
                    "s1_principal_stockholders", "s1_use_of_proceeds",
                    "s1_capitalization", "s1_dilution", "s1_underwriting",
                )},
                counterparty_context="",
                macro_indicators="",
            )

        self.assertIn("Business Quality", out.failures)
        self.assertEqual(len(out.results), 6)
