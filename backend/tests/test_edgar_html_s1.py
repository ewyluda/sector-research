"""Section extraction tests for S-1 / S-1/A filings."""
import unittest

from backend.app.services.edgar_html import extract_sections


def _fake_s1_html(*, business=True, risks=True, mda=True,
                  proceeds=True, capitalization=True, dilution=True,
                  principal=True, underwriting=True) -> str:
    """Construct a synthetic S-1 HTML body. Each section gets >500 chars so
    extract_sections's MIN_SECTION_CHARS gate is satisfied. Boundary text
    between sections caps the prior section's body.
    """
    pad = " The following paragraph contains substantive narrative content " * 10  # ~640 chars

    parts: list[str] = ["<html><body>"]
    if business:
        parts.append(f"<p>ITEM 1. BUSINESS</p><p>We design, manufacture and launch rockets.{pad}</p>")
    if risks:
        parts.append(f"<p>RISK FACTORS</p><p>Our business is subject to many risks.{pad}</p>")
    if mda:
        parts.append(f"<p>MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</p>"
                     f"<p>Revenues for the year ended Dec 31, 2024 were $14.0 billion.{pad}</p>")
    if proceeds:
        parts.append(f"<p>USE OF PROCEEDS</p><p>We intend to use the net proceeds for general corporate purposes.{pad}</p>")
    if capitalization:
        parts.append(f"<p>CAPITALIZATION</p><p>The following table sets forth our capitalization.{pad}</p>")
    if dilution:
        parts.append(f"<p>DILUTION</p><p>If you invest in our Class A common stock you will experience dilution.{pad}</p>")
    if principal:
        parts.append(f"<p>PRINCIPAL STOCKHOLDERS</p><p>The following table sets forth our principal stockholders.{pad}</p>")
    if underwriting:
        parts.append(f"<p>UNDERWRITING</p><p>Subject to the terms and conditions of the underwriting agreement.{pad}</p>")
    parts.append("</body></html>")
    return "".join(parts)


class TestS1Sections(unittest.TestCase):
    def test_all_eight_sections_extracted(self):
        sections = extract_sections(_fake_s1_html(), "S-1")
        keys = {s.section_key for s in sections}
        self.assertEqual(keys, {
            "s1_business", "s1_risk_factors", "s1_mda",
            "s1_use_of_proceeds", "s1_capitalization", "s1_dilution",
            "s1_principal_stockholders", "s1_underwriting",
        })

    def test_s1a_uses_same_defs(self):
        sections = extract_sections(_fake_s1_html(), "S-1/A")
        keys = {s.section_key for s in sections}
        self.assertIn("s1_business", keys)
        self.assertIn("s1_underwriting", keys)

    def test_missing_section_silently_skipped(self):
        sections = extract_sections(_fake_s1_html(dilution=False), "S-1")
        keys = {s.section_key for s in sections}
        self.assertNotIn("s1_dilution", keys)
        self.assertIn("s1_business", keys)
