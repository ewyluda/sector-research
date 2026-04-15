"""Extract narrative sections from SEC EDGAR filing HTML.

For a given filing HTML (10-K, 10-Q, or DEF 14A) returns the business,
risk-factors, MD&A, and governance sections as plain text. The full text is
stored in `filing_sections`; prompt builders truncate to per-category budgets.

Strategy
--------
1. Strip inline XBRL — unwrap `<ix:nonFraction>` / `<ix:nonNumeric>` so their
   displayed value is preserved, drop `<ix:hidden>` entirely.
2. Normalize the full document text (NBSP collapse, whitespace normalization).
3. For each section_key defined per form type, run regex over the normalized
   text. Because 10-Ks typically mention each Item heading in the TOC *and*
   in the actual body, we collect all matches per key and pick the one whose
   body-to-next-section is longest — that's the real section, not a TOC entry
   or cross-reference.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# EDGAR filings are inline-XBRL HTML — BS4's lxml parser warns about the
# XML declaration. Suppress at module level; we're deliberately parsing the
# displayed HTML, not the XBRL schema.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


@dataclass
class ExtractedSection:
    section_key: str
    heading: str
    text: str
    char_count: int
    extraction_method: str  # "regex" (v1); "anchor" reserved for future


# Per-form section definitions.
# Each entry: (section_key, [regex patterns]). First matching pattern wins.
# Sentinel prefix — boundary markers that cap the preceding section's body
# but are not themselves emitted as extracted sections.
_BOUNDARY_PREFIX = "_boundary_"

_SECTION_DEFS_10K: list[tuple[str, list[str]]] = [
    ("item_1_business", [r"\bITEM\s*1\.?\s*BUSINESS\b"]),
    ("item_1a_risk_factors", [r"\bITEM\s*1A\.?\s*RISK\s+FACTORS\b"]),
    # Boundary so item_1a doesn't bleed past Item 1B.
    (_BOUNDARY_PREFIX + "item_1b", [r"\bITEM\s*1B\.?\s*UNRESOLVED"]),
    (_BOUNDARY_PREFIX + "item_2", [r"\bITEM\s*2\.?\s*PROPERTIES\b"]),
    ("item_7_mda", [r"\bITEM\s*7\.?\s*MANAGEMENT['\u2019]?S\s+DISCUSSION"]),
    # Boundaries so item_7 doesn't bleed into 7A / 8 / 9 / signatures.
    (_BOUNDARY_PREFIX + "item_7a", [r"\bITEM\s*7A\.?\s*QUANTITATIVE"]),
    (_BOUNDARY_PREFIX + "item_8", [r"\bITEM\s*8\.?\s*FINANCIAL\s+STATEMENTS"]),
    (_BOUNDARY_PREFIX + "item_9", [r"\bITEM\s*9\.?\s*CHANGES\s+IN\s+AND\s+DISAGREEMENTS"]),
]

_SECTION_DEFS_10Q: list[tuple[str, list[str]]] = [
    ("item_2_mda_10q", [r"\bITEM\s*2\.?\s*MANAGEMENT['\u2019]?S\s+DISCUSSION"]),
    (_BOUNDARY_PREFIX + "item_3_10q", [r"\bITEM\s*3\.?\s*QUANTITATIVE"]),
    (_BOUNDARY_PREFIX + "item_4_10q", [r"\bITEM\s*4\.?\s*CONTROLS\s+AND\s+PROCEDURES"]),
    ("item_1a_risk_factors", [r"\bITEM\s*1A\.?\s*RISK\s+FACTORS\b"]),
    (_BOUNDARY_PREFIX + "part2_item_2_10q", [r"\bITEM\s*2\.?\s*UNREGISTERED\s+SALES"]),
]

_SECTION_DEFS_DEF14A: list[tuple[str, list[str]]] = [
    ("def14a_governance", [
        r"\bCORPORATE\s+GOVERNANCE\b",
        r"\bBOARD\s+OF\s+DIRECTORS\b",
    ]),
    (_BOUNDARY_PREFIX + "compensation", [r"\bEXECUTIVE\s+COMPENSATION\b"]),
    (_BOUNDARY_PREFIX + "audit", [r"\bAUDIT\s+COMMITTEE\s+REPORT\b"]),
]

MIN_SECTION_CHARS = 500


def _clean_inline_xbrl(soup: BeautifulSoup) -> BeautifulSoup:
    """Drop hidden XBRL, unwrap displayed XBRL, drop scripts/styles."""
    # bs4 with `lxml` lowercases tag names; match case-insensitively.
    HIDDEN_TAGS = {"ix:hidden"}
    UNWRAP_TAGS = {
        "ix:nonfraction",
        "ix:nonnumeric",
        "ix:fraction",
        "ix:numerator",
        "ix:denominator",
        "ix:continuation",
    }
    DROP_TAGS = {"script", "style"}

    for tag in list(soup.find_all(lambda t: t.name and t.name.lower() in HIDDEN_TAGS)):
        tag.decompose()

    for tag in list(soup.find_all(lambda t: t.name and t.name.lower() in DROP_TAGS)):
        tag.decompose()

    for tag in list(soup.find_all(lambda t: t.name and t.name.lower() in UNWRAP_TAGS)):
        tag.unwrap()

    return soup


def _normalize_text(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _pick_section_defs(form_type: str) -> list[tuple[str, list[str]]]:
    key = form_type.upper().replace(" ", "").replace("/", "")
    if "10-K" in key or "10K" in key:
        return _SECTION_DEFS_10K
    if "10-Q" in key or "10Q" in key:
        return _SECTION_DEFS_10Q
    if "DEF14A" in key:
        return _SECTION_DEFS_DEF14A
    return []


def extract_sections(html: str, form_type: str) -> list[ExtractedSection]:
    """Extract narrative sections from a filing HTML string.

    Returns a list of ExtractedSection, one per section_key that was found with
    a body of at least MIN_SECTION_CHARS. Sections not present in the filing
    are silently omitted.
    """
    defs = _pick_section_defs(form_type)
    if not defs:
        return []

    soup = BeautifulSoup(html, "lxml")
    _clean_inline_xbrl(soup)
    full_text = _normalize_text(soup.get_text(separator="\n"))
    if len(full_text) < MIN_SECTION_CHARS:
        return []

    # Collect every match across every section pattern.
    all_matches: list[tuple[int, int, str, str]] = []
    for section_key, patterns in defs:
        for pat in patterns:
            for m in re.finditer(pat, full_text, re.IGNORECASE):
                all_matches.append((m.start(), m.end(), section_key, m.group(0)))

    if not all_matches:
        return []

    all_matches.sort()

    # For each section_key, find the match whose body (to the next
    # differently-keyed match, or end-of-document) is the longest.
    best_by_key: dict[str, tuple[int, str, str]] = {}  # key -> (body_len, heading, body)
    for i, (start, end, key, heading) in enumerate(all_matches):
        next_start = len(full_text)
        for j in range(i + 1, len(all_matches)):
            if all_matches[j][2] != key:
                next_start = all_matches[j][0]
                break
        body = full_text[end:next_start].strip()
        body_len = len(body)
        if body_len < MIN_SECTION_CHARS:
            continue
        prev = best_by_key.get(key)
        if prev is None or body_len > prev[0]:
            best_by_key[key] = (body_len, heading, body)

    # Preserve section_key ordering from the defs list. Skip boundary markers.
    results: list[ExtractedSection] = []
    for section_key, _ in defs:
        if section_key.startswith(_BOUNDARY_PREFIX):
            continue
        hit = best_by_key.get(section_key)
        if not hit:
            continue
        _, heading, body = hit
        results.append(ExtractedSection(
            section_key=section_key,
            heading=heading,
            text=body,
            char_count=len(body),
            extraction_method="regex",
        ))
    return results
