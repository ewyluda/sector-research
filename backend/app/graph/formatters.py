"""Data-formatting helpers extracted from nodes.py (M2.2).

This module holds the pure functions that transform raw FMP/FRED data into
prompt-ready strings and frontend-ready curated payloads.  No LLM calls, no
DB access.  Extracted from ``backend.app.graph.nodes`` as part of the M2.2
campaign; all names and signatures are unchanged.

Symbols exported:
  _extract_score
  _extract_key_findings
  _first_metric
  _fmt_fundamentals
  _build_curated_financials
  _build_technical_data
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from backend.app.services.quant_fingerprint import build_quant_fingerprint

if TYPE_CHECKING:
    from backend.app.graph.state import CuratedFinancials

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_score(text: str) -> int:
    """Parse 'SCORE: XX/100' or 'CONVICTION: XX/100' from LLM output."""
    for pattern in [r"(?:SCORE|CONVICTION):\s*(\d+)/100", r"(\d+)/100"]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return min(100, max(0, int(m.group(1))))
    return 50  # default if not found


def _extract_key_findings(text: str) -> list[str]:
    """Pull bullet points from the 'Key findings' section."""
    lines = text.split("\n")
    findings = []
    in_findings = False
    for line in lines:
        if "key finding" in line.lower():
            in_findings = True
            continue
        if in_findings:
            stripped = line.strip().lstrip("•-*123456789. ")
            if stripped and len(stripped) > 10:
                findings.append(stripped)
            if len(findings) >= 5:
                break
            if line.strip() == "" and findings:
                break
    return findings


def _first_metric(*candidates: tuple[dict | None, str]) -> float | None:
    """First non-None float across (dict, key) candidates — same contract as
    services.peer_comp._first; lives here to keep graph/ free of service imports.

    Distinct from `x or y` — a legitimate 0.0 value short-circuits correctly.
    """
    for d, key in candidates:
        if not isinstance(d, dict):
            continue
        v = d.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _fv(val: Any, divisor: float = 1e9, suffix: str = "B") -> str:
    """Format a financial value as a dollar amount."""
    if val is None or val == 0:
        return "N/A"
    return f"${val / divisor:.2f}{suffix}"


def _fmt_profile_section(ticker: str, profile: dict) -> list[str]:
    """Company profile: name, sector, market cap, beta, description."""
    if not (profile and isinstance(profile, dict)):
        return []
    return [
        f"Company: {profile.get('companyName', ticker)}",
        f"Sector: {profile.get('sector')} | Industry: {profile.get('industry')}",
        f"Market Cap: ${profile.get('marketCap', 0)/1e9:.1f}B",
        f"Beta: {profile.get('beta', 'N/A')}",
        f"Description: {str(profile.get('description', ''))[:300]}",
    ]


def _fmt_valuation_section(key_metrics: dict | None, ratios: dict | None) -> list[str]:
    """Valuation ratios and return metrics (TTM).

    ratios-ttm first, legacy key-metrics-ttm fallback
    (the /stable/ API serves multiples on ratios-ttm; live-verified 2026-06-09).
    """
    rt = ratios if isinstance(ratios, dict) else {}
    km = key_metrics if isinstance(key_metrics, dict) else {}
    if not (rt or km):
        return []
    parts: list[str] = ["\nValuation Ratios (TTM):"]
    for label, candidates in [
        ("P/E", ((rt, "priceToEarningsRatioTTM"), (km, "peRatioTTM"))),
        ("EV/EBITDA", ((rt, "enterpriseValueMultipleTTM"), (km, "enterpriseValueOverEBITDATTM"))),
        ("P/B", ((rt, "priceToBookRatioTTM"), (km, "priceToBookRatioTTM"))),
        ("P/FCF", ((rt, "priceToFreeCashFlowRatioTTM"), (km, "priceToFreeCashFlowsRatioTTM"))),
        ("P/S", ((rt, "priceToSalesRatioTTM"), (km, "priceToSalesRatioTTM"))),
        ("PEG", ((rt, "priceToEarningsGrowthRatioTTM"), (km, "pegRatioTTM"))),
        ("Dividend Yield", ((rt, "dividendYieldTTM"), (km, "dividendYieldTTM"))),
    ]:
        v = _first_metric(*candidates)
        if v is not None:
            if "Yield" in label:
                parts.append(f"  {label}: {v*100:.2f}%")
            else:
                parts.append(f"  {label}: {v:.2f}")

    parts.append("\nReturn Metrics (TTM):")
    for label, candidates in [
        ("ROE", ((km, "returnOnEquityTTM"), (km, "roeTTM"))),
        ("ROIC", ((km, "returnOnInvestedCapitalTTM"), (km, "roicTTM"))),
        ("ROA", ((km, "returnOnAssetsTTM"), (km, "returnOnTangibleAssetsTTM"))),
    ]:
        v = _first_metric(*candidates)
        if v is not None:
            parts.append(f"  {label}: {v*100:.1f}%")

    ic = _first_metric((rt, "interestCoverageRatioTTM"), (km, "interestCoverageTTM"))
    if ic is not None:
        parts.append(f"  Interest Coverage: {ic:.1f}x")
    return parts


def _fmt_income_trends_section(income: list) -> list[str]:
    """Quarterly income statement (up to 8Q) with YoY growth."""
    if not income:
        return []
    parts: list[str] = [f"\nQuarterly Income Statement ({len(income)} quarters, newest first):"]
    for i, stmt in enumerate(income[:8]):
        rev = stmt.get("revenue", 0) or 0
        gp = stmt.get("grossProfit", 0) or 0
        oi = stmt.get("operatingIncome", 0) or 0
        ni = stmt.get("netIncome", 0) or 0
        eps = stmt.get("eps", "N/A")
        gm = f"{gp/rev*100:.1f}%" if rev else "N/A"
        om = f"{oi/rev*100:.1f}%" if rev else "N/A"
        nm = f"{ni/rev*100:.1f}%" if rev else "N/A"
        # YoY growth (compare to same quarter one year ago = i+4)
        yoy = ""
        if i + 4 < len(income):
            prev_rev = income[i + 4].get("revenue", 0) or 0
            if prev_rev:
                yoy = f" (YoY: {(rev - prev_rev)/abs(prev_rev)*100:+.1f}%)"
        period = stmt.get("period", "") or stmt.get("date", "")[:7]
        parts.append(f"  {period}: Rev {_fv(rev)} {yoy} | GM {gm} | OM {om} | NM {nm} | EPS {eps}")
    return parts


def _fmt_balance_sheet_section(balance: list, income: list) -> list[str]:
    """Balance sheet (last 4Q) with debt structure and interest expense."""
    if not balance:
        return []
    parts: list[str] = [f"\nBalance Sheet ({len(balance)} quarters, newest first):"]
    for stmt in balance[:4]:
        period = stmt.get("period", "") or stmt.get("date", "")[:7]
        cash = stmt.get("cashAndCashEquivalents", 0) or 0
        st_debt = stmt.get("shortTermDebt", 0) or 0
        lt_debt = stmt.get("longTermDebt", 0) or 0
        total_debt = stmt.get("totalDebt", 0) or 0
        equity = stmt.get("totalEquity", 0) or stmt.get("totalStockholdersEquity", 0) or 0
        ca = stmt.get("totalCurrentAssets", 0) or 0
        cl = stmt.get("totalCurrentLiabilities", 0) or 0
        cr = f"{ca/cl:.2f}" if cl else "N/A"
        de = f"{total_debt/equity:.2f}" if equity else "N/A"
        parts.append(f"  {period}: Cash {_fv(cash)} | ST Debt {_fv(st_debt)} | LT Debt {_fv(lt_debt)} | D/E {de} | Current Ratio {cr}")

    # Interest expense from latest income statement
    if income:
        ie = income[0].get("interestExpense", 0) or 0
        if ie:
            parts.append(f"  Latest Interest Expense: {_fv(abs(ie))}")
    return parts


def _fmt_cashflow_section(cashflow: list) -> list[str]:
    """Cash flow statement (last 4Q): OCF, FCF, CapEx, SBC."""
    if not cashflow:
        return []
    parts: list[str] = [f"\nCash Flow ({len(cashflow)} quarters, newest first):"]
    for stmt in cashflow[:4]:
        period = stmt.get("period", "") or stmt.get("date", "")[:7]
        ocf = stmt.get("operatingCashFlow", 0) or 0
        fcf = stmt.get("freeCashFlow", 0) or 0
        capex = stmt.get("capitalExpenditure", 0) or 0
        sbc = stmt.get("stockBasedCompensation", 0) or 0
        parts.append(f"  {period}: OCF {_fv(ocf)} | FCF {_fv(fcf)} | CapEx {_fv(capex)} | SBC {_fv(sbc)}")
    return parts


def _fmt_dcf_section(dcf: dict | None) -> list[str]:
    """DCF intrinsic value with gap-to-current-price."""
    if not (dcf and isinstance(dcf, dict)):
        return []
    dcf_val = dcf.get("dcf")
    if not dcf_val:
        return []
    stock_price = dcf.get("Stock Price") or dcf.get("stockPrice")
    gap = ""
    if stock_price and float(stock_price) > 0:
        gap_pct = (float(dcf_val) - float(stock_price)) / float(stock_price) * 100
        gap = f" ({gap_pct:+.1f}% vs current)"
    return [f"\nDCF Intrinsic Value: ${dcf_val}{gap}"]


def _fmt_estimates_section(estimates: list | None) -> list[str]:
    """Forward analyst estimates with earnings surprise (up to 4Q)."""
    if not estimates:
        return []
    parts: list[str] = [f"\nAnalyst Estimates ({len(estimates)} quarters):"]
    for est in estimates[:4]:
        period = est.get("date", "")[:7]
        rev_est = est.get("estimatedRevenueAvg") or est.get("revenueAvg")
        eps_est = est.get("estimatedEpsAvg") or est.get("epsAvg")
        rev_act = est.get("actualRevenue")
        eps_act = est.get("actualEps")
        line = f"  {period}:"
        if rev_est is not None:
            line += f" Rev Est {_fv(rev_est)}"
            if rev_act is not None:
                surprise = (float(rev_act) - float(rev_est)) / abs(float(rev_est)) * 100 if float(rev_est) else 0
                line += f" → Actual {_fv(rev_act)} ({surprise:+.1f}% surprise)"
        if eps_est is not None:
            line += f" | EPS Est ${float(eps_est):.2f}"
            if eps_act is not None:
                line += f" → Actual ${float(eps_act):.2f} ({float(eps_act) - float(eps_est):+.2f})"
        parts.append(line)
    return parts


def _fmt_growth_section(fin_growth: list | None) -> list[str]:
    """Historical revenue / EPS / FCF growth rates (up to 4Q)."""
    if not fin_growth:
        return []
    parts: list[str] = [f"\nGrowth Rates ({len(fin_growth)} quarters):"]
    for g in fin_growth[:4]:
        period = g.get("date", "")[:7]
        rg = g.get("revenueGrowth")
        eg = g.get("epsgrowth") or g.get("epsGrowth")
        fcfg = g.get("freeCashFlowGrowth")
        line = f"  {period}:"
        if rg is not None:
            line += f" Rev Growth {float(rg)*100:+.1f}%"
        if eg is not None:
            line += f" | EPS Growth {float(eg)*100:+.1f}%"
        if fcfg is not None:
            line += f" | FCF Growth {float(fcfg)*100:+.1f}%"
        parts.append(line)
    return parts


def _fmt_analyst_consensus_section(
    profile: dict,
    grade_consensus: dict | None,
    price_target: dict | None,
    ratings_snap: dict | None,
) -> list[str]:
    """Analyst consensus, price target, and FMP composite rating."""
    if not (grade_consensus or price_target or ratings_snap):
        return []
    parts: list[str] = ["\nAnalyst Consensus & Ratings:"]
    if isinstance(grade_consensus, dict) and grade_consensus:
        sb = grade_consensus.get("strongBuy") or 0
        b = grade_consensus.get("buy") or 0
        h = grade_consensus.get("hold") or 0
        s = grade_consensus.get("sell") or 0
        ss = grade_consensus.get("strongSell") or 0
        total = sb + b + h + s + ss
        label = grade_consensus.get("consensus") or "N/A"
        parts.append(
            f"  Consensus: {label} (StrongBuy {sb} / Buy {b} / Hold {h} / Sell {s} / StrongSell {ss}; {total} analysts)"
        )
    if isinstance(price_target, dict) and price_target:
        tc = price_target.get("targetConsensus")
        th = price_target.get("targetHigh")
        tl = price_target.get("targetLow")
        tm = price_target.get("targetMedian")
        current = profile.get("price") if isinstance(profile, dict) else None
        line = "  Price Target:"
        if tc is not None:
            line += f" avg ${float(tc):.2f}"
        if tm is not None:
            line += f" | median ${float(tm):.2f}"
        if th is not None and tl is not None:
            line += f" | range ${float(tl):.2f}–${float(th):.2f}"
        if current and tc:
            upside = (float(tc) - float(current)) / float(current) * 100
            line += f" | implied {upside:+.1f}% vs current ${float(current):.2f}"
        parts.append(line)
    if isinstance(ratings_snap, dict) and ratings_snap:
        rating = ratings_snap.get("rating")
        score = ratings_snap.get("overallScore")
        if rating or score is not None:
            parts.append(f"  FMP Rating: {rating or 'N/A'} (overall score {score}/5)")
    return parts


def _fmt_grades_recent_section(grades_recent: list | None) -> list[str]:
    """Recent analyst rating changes (upgrade / downgrade events)."""
    if not (isinstance(grades_recent, list) and grades_recent):
        return []
    parts: list[str] = [f"\nRecent Analyst Actions ({len(grades_recent[:8])} most recent):"]
    for g in grades_recent[:8]:
        date_ = g.get("date", "")[:10]
        firm = g.get("gradingCompany") or "Unknown"
        prev = g.get("previousGrade") or "—"
        new = g.get("newGrade") or "—"
        action = g.get("action") or ""
        parts.append(f"  {date_} {firm}: {prev} → {new} ({action})")
    return parts


def _fmt_grades_hist_section(grades_hist: list | None) -> list[str]:
    """Analyst consensus count trend (monthly, last 4 months)."""
    if not (isinstance(grades_hist, list) and grades_hist):
        return []
    parts: list[str] = ["\nAnalyst Consensus Trend (monthly):"]
    for row in grades_hist[:4]:
        date_ = row.get("date", "")[:7]
        sb = row.get("analystRatingsStrongBuy") or 0
        b = row.get("analystRatingsBuy") or 0
        h = row.get("analystRatingsHold") or 0
        s = row.get("analystRatingsSell") or 0
        ss = row.get("analystRatingsStrongSell") or 0
        parts.append(f"  {date_}: SB {sb} / B {b} / H {h} / S {s} / SS {ss}")
    return parts


def _fmt_insider_tx_section(insider_tx: list | None) -> list[str]:
    """Insider transactions (Form 4s — market-priced only, last 6 shown)."""
    if not (isinstance(insider_tx, list) and insider_tx):
        return []
    # Filter to market-priced transactions — zero-price rows are usually
    # option grants or gifts and don't indicate conviction.
    meaningful = [
        t for t in insider_tx
        if float(t.get("securitiesTransacted") or 0) > 0
        and float(t.get("price") or 0) > 0
    ]
    if not meaningful:
        return []
    # Aggregate buys vs sells (A = acquisition, D = disposition) for a quick summary
    buys = sum(
        float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
        for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "A"
    )
    sells = sum(
        float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
        for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "D"
    )
    parts: list[str] = [f"\nInsider Transactions (last {len(meaningful)} Form 4 filings):"]
    parts.append(
        f"  Aggregate: ${buys/1e6:.2f}M buys vs ${sells/1e6:.2f}M sells (net ${(buys-sells)/1e6:+.2f}M)"
    )
    for t in meaningful[:6]:
        fdate = (t.get("filingDate") or "")[:10]
        name = t.get("reportingName") or "Unknown"
        role = t.get("typeOfOwner") or ""
        shares = float(t.get("securitiesTransacted") or 0)
        price = float(t.get("price") or 0)
        direction = "BUY" if (t.get("acquisitionOrDisposition") or "").upper() == "A" else "SELL"
        value = shares * price
        parts.append(
            f"  {fdate} {name} ({role}): {direction} {shares:,.0f} sh @ ${price:.2f} = ${value/1e6:.2f}M"
        )
    return parts


def _humanize(val: float | int | None) -> str:
    """Humanize a large number: 1.2B, 450M, 3.1K, or plain int for small values."""
    if val is None:
        return "—"
    v = float(val)
    if abs(v) >= 1e9:
        return f"{v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"


def _section_institutional(
    inst_summary: dict | None,
    inst_holders: list | None,
) -> str:
    """13F institutional ownership section (filings-lag framed)."""
    if not inst_summary and not inst_holders:
        return ""

    parts: list[str] = []

    if inst_summary and isinstance(inst_summary, dict):
        quarter_date = inst_summary.get("date") or "unknown quarter-end"
        parts.append(
            f"\nINSTITUTIONAL OWNERSHIP (13F, as of {quarter_date} quarter-end"
            " — filings lag ≥45 days; positioning context, NOT current data):"
        )

        # Holders count + 13F shares + ownership %
        holders = inst_summary.get("investorsHolding")
        holders_chg = inst_summary.get("investorsHoldingChange")
        shares13f = inst_summary.get("numberOf13Fshares")
        shares13f_chg = inst_summary.get("numberOf13FsharesChange")
        own_pct = inst_summary.get("ownershipPercent")

        holders_str = f"{holders:,}" if holders is not None else "—"
        holders_chg_str = f" ({holders_chg:+,} QoQ)" if holders_chg is not None else ""
        shares_str = _humanize(shares13f)
        shares_chg_str = (
            f" ({_humanize(shares13f_chg)} QoQ)" if shares13f_chg is not None else ""
        )
        own_str = f"{own_pct:.1f}%" if own_pct is not None else "—"
        parts.append(
            f"  Holders: {holders_str}{holders_chg_str}"
            f" | 13F shares: {shares_str}{shares_chg_str}"
            f" | {own_str} of shares"
        )

        # Position churn
        new_pos = inst_summary.get("newPositions")
        inc_pos = inst_summary.get("increasedPositions")
        red_pos = inst_summary.get("reducedPositions")
        cls_pos = inst_summary.get("closedPositions")
        if any(v is not None for v in (new_pos, inc_pos, red_pos, cls_pos)):
            parts.append(
                f"  Position churn QoQ:"
                f" {new_pos if new_pos is not None else '—'} new"
                f" / {inc_pos if inc_pos is not None else '—'} increased"
                f" / {red_pos if red_pos is not None else '—'} reduced"
                f" / {cls_pos if cls_pos is not None else '—'} closed"
            )

        # Put/call ratio
        pcr = inst_summary.get("putCallRatio")
        pcr_chg = inst_summary.get("putCallRatioChange")
        if pcr is not None:
            pcr_chg_str = f" ({pcr_chg:+.1f}% QoQ)" if pcr_chg is not None else ""
            parts.append(f"  13F options positioning: put/call {pcr:.2f}{pcr_chg_str}")
    else:
        # holders-only path — still emit the header without a date
        parts.append(
            "\nINSTITUTIONAL OWNERSHIP (13F"
            " — filings lag ≥45 days; positioning context, NOT current data):"
        )

    # Top holders
    if isinstance(inst_holders, list) and inst_holders:
        sorted_holders = sorted(
            inst_holders,
            key=lambda h: float(h.get("marketValue") or 0),
            reverse=True,
        )
        parts.append("Top holders (by market value):")
        for h in sorted_holders[:10]:
            name = (h.get("investorName") or "Unknown")[:40]
            shares = h.get("sharesNumber")
            mv = h.get("marketValue")
            chg_shares = h.get("changeInSharesNumber")
            is_new = h.get("isNew", False)

            shares_str = _humanize(shares)
            mv_str = _humanize(mv)

            line = f"  {name} — {shares_str} sh (${mv_str})"
            if chg_shares and float(chg_shares) != 0:
                line += f", {_humanize(chg_shares)} sh QoQ"
            if is_new:
                line += " [NEW]"
            parts.append(line)

    return "\n".join(parts)


def _fmt_fundamentals(
    ticker: str,
    income: list,
    balance: list,
    cashflow: list,
    profile: dict,
    *,
    dcf: dict | None = None,
    estimates: list | None = None,
    key_metrics: dict | None = None,
    ratios: dict | None = None,
    fin_growth: list | None = None,
    grade_consensus: dict | None = None,
    price_target: dict | None = None,
    ratings_snap: dict | None = None,
    grades_recent: list | None = None,
    grades_hist: list | None = None,
    insider_tx: list | None = None,
    inst_summary: dict | None = None,
    inst_holders: list | None = None,
) -> str:
    """Format raw FMP data into a comprehensive block for LLM prompts.

    Includes multi-quarter trends, valuation ratios, return metrics,
    debt structure, forward estimates, and earnings surprises.

    Thin composer: delegates each section to a private per-section helper
    so each helper is independently testable.
    """
    parts: list[str] = []
    parts.extend(_fmt_profile_section(ticker, profile))
    parts.extend(_fmt_valuation_section(key_metrics, ratios))
    parts.extend(_fmt_income_trends_section(income))
    parts.extend(_fmt_balance_sheet_section(balance, income))
    parts.extend(_fmt_cashflow_section(cashflow))
    parts.extend(_fmt_dcf_section(dcf))
    parts.extend(_fmt_estimates_section(estimates))
    parts.extend(_fmt_growth_section(fin_growth))
    parts.extend(_fmt_analyst_consensus_section(profile, grade_consensus, price_target, ratings_snap))
    parts.extend(_fmt_grades_recent_section(grades_recent))
    parts.extend(_fmt_grades_hist_section(grades_hist))
    parts.extend(_fmt_insider_tx_section(insider_tx))
    inst_section = _section_institutional(inst_summary, inst_holders)
    if inst_section:
        parts.append(inst_section)
    return "\n".join(parts)


def _build_curated_financials(
    ticker: str,
    income: list[dict],
    balance: list[dict],
    cashflow: list[dict],
    profile: dict,
    dcf: dict | None,
    estimates: list[dict],
    key_metrics: dict | None = None,
    ratios: dict | None = None,
) -> "CuratedFinancials":
    """Extract a curated subset of FMP data for frontend dashboard charts."""
    from backend.app.graph.state import CuratedFinancials, QuarterlyMetric, EstimateMetric

    def safe_div(a: float, b: float) -> float | None:
        return a / b if b else None

    def pct(a: float, b: float) -> float | None:
        return ((a - b) / abs(b)) * 100 if b else None

    def make_quarterly(statements: list[dict], field_name: str) -> list[QuarterlyMetric]:
        """Build QuarterlyMetric list from a series of FMP statements."""
        metrics = []
        for i, stmt in enumerate(statements):
            val = stmt.get(field_name, 0) or 0
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
            prev_val = statements[i + 1].get(field_name, 0) if i + 1 < len(statements) else None
            yoy = pct(val, prev_val) if prev_val else None
            metrics.append(QuarterlyMetric(period=period, value=float(val), yoy_growth=yoy))
        return metrics

    def make_margin(statements: list[dict], numerator: str, denominator: str = "revenue") -> list[QuarterlyMetric]:
        """Build margin % metrics."""
        metrics = []
        for stmt in statements:
            rev = stmt.get(denominator, 0) or 0
            num = stmt.get(numerator, 0) or 0
            margin = (num / rev * 100) if rev else 0
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
            metrics.append(QuarterlyMetric(period=period, value=round(margin, 2), yoy_growth=None))
        return metrics

    # Profile data
    prof = profile or {}
    company_name = prof.get("companyName", ticker)
    sector = prof.get("sector", "")
    industry = prof.get("industry", "")
    market_cap = float(prof.get("mktCap", 0) or prof.get("marketCap", 0) or 0)
    current_price = float(prof.get("price", 0) or 0)
    beta = prof.get("beta")
    beta = float(beta) if beta is not None else None
    vol_avg = prof.get("volAvg")
    vol_avg = float(vol_avg) if vol_avg is not None else None
    range_str = prof.get("range", "")
    fifty_two_low, fifty_two_high = None, None
    if range_str and "-" in range_str:
        parts = range_str.split("-")
        try:
            fifty_two_low = float(parts[0].strip())
            fifty_two_high = float(parts[1].strip())
        except (ValueError, IndexError):
            pass

    # DCF
    dcf_value = None
    dcf_gap = None
    if dcf and isinstance(dcf, dict):
        dcf_value = dcf.get("dcf")
        dcf_value = float(dcf_value) if dcf_value is not None else None
        stock_price = dcf.get("Stock Price") or dcf.get("stockPrice") or current_price
        if dcf_value and stock_price:
            dcf_gap = round((dcf_value - float(stock_price)) / float(stock_price) * 100, 2)

    # Balance sheet ratios
    d_e = 0.0
    if balance:
        b0 = balance[0]
        debt = float(b0.get("totalDebt", 0) or 0)
        equity = float(b0.get("totalEquity", 0) or b0.get("totalStockholdersEquity", 0) or 0)
        d_e = round(debt / equity, 2) if equity else 0.0

    def make_current_ratio(bs: list[dict]) -> list[QuarterlyMetric]:
        metrics = []
        for stmt in bs:
            ca = float(stmt.get("totalCurrentAssets", 0) or 0)
            cl = float(stmt.get("totalCurrentLiabilities", 0) or 0)
            cr = round(ca / cl, 2) if cl else 0
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
            metrics.append(QuarterlyMetric(period=period, value=cr, yoy_growth=None))
        return metrics

    # Estimates
    fwd_rev = []
    fwd_eps = []
    for est in (estimates or []):
        period = est.get("date", "")[:7]
        rev_est = est.get("estimatedRevenueAvg") or est.get("revenueAvg")
        eps_est = est.get("estimatedEpsAvg") or est.get("epsAvg")
        rev_act = est.get("actualRevenue")
        eps_act = est.get("actualEps")
        if rev_est is not None:
            fwd_rev.append(EstimateMetric(period=period, estimate=float(rev_est), actual=float(rev_act) if rev_act is not None else None))
        if eps_est is not None:
            fwd_eps.append(EstimateMetric(period=period, estimate=float(eps_est), actual=float(eps_act) if eps_act is not None else None))

    # Valuation + returns — ratios-ttm first, legacy key-metrics-ttm fallback
    # (same wire-name mapping as _fmt_fundamentals / services.peer_comp._fetch_one)
    km = key_metrics or {}
    rt = ratios or {}

    curated = CuratedFinancials(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        market_cap=market_cap,
        current_price=current_price,
        quarterly_revenue=make_quarterly(income, "revenue"),
        quarterly_eps=make_quarterly(income, "eps"),
        quarterly_gross_margin=make_margin(income, "grossProfit"),
        quarterly_operating_margin=make_margin(income, "operatingIncome"),
        quarterly_net_margin=make_margin(income, "netIncome"),
        quarterly_cash=make_quarterly(balance, "cashAndCashEquivalents"),
        quarterly_total_debt=make_quarterly(balance, "totalDebt"),
        quarterly_shareholders_equity=make_quarterly(balance, "totalEquity"),
        quarterly_current_ratio=make_current_ratio(balance),
        debt_to_equity=d_e,
        quarterly_operating_cf=make_quarterly(cashflow, "operatingCashFlow"),
        quarterly_free_cf=make_quarterly(cashflow, "freeCashFlow"),
        quarterly_capex=make_quarterly(cashflow, "capitalExpenditure"),
        dcf_intrinsic_value=dcf_value,
        dcf_gap_percent=dcf_gap,
        forward_revenue_estimates=fwd_rev,
        forward_eps_estimates=fwd_eps,
        pe_ratio=_first_metric((rt, "priceToEarningsRatioTTM"), (km, "peRatioTTM")),
        ev_to_ebitda=_first_metric((rt, "enterpriseValueMultipleTTM"), (km, "enterpriseValueOverEBITDATTM")),
        price_to_book=_first_metric((rt, "priceToBookRatioTTM"), (km, "priceToBookRatioTTM")),
        price_to_fcf=_first_metric((rt, "priceToFreeCashFlowRatioTTM"), (km, "priceToFreeCashFlowsRatioTTM")),
        price_to_sales=_first_metric((rt, "priceToSalesRatioTTM"), (km, "priceToSalesRatioTTM")),
        peg_ratio=_first_metric((rt, "priceToEarningsGrowthRatioTTM"), (km, "pegRatioTTM")),
        roe=_first_metric((km, "returnOnEquityTTM"), (km, "roeTTM")),
        roic=_first_metric((km, "returnOnInvestedCapitalTTM"), (km, "roicTTM")),
        roa=_first_metric((km, "returnOnAssetsTTM"), (km, "returnOnTangibleAssetsTTM")),
        interest_coverage=_first_metric((rt, "interestCoverageRatioTTM"), (km, "interestCoverageTTM")),
        dividend_yield=_first_metric((rt, "dividendYieldTTM"), (km, "dividendYieldTTM")),
        beta=beta,
        fifty_two_week_high=fifty_two_high,
        fifty_two_week_low=fifty_two_low,
        volume_avg=vol_avg,
    )
    # Defensive: a quant bug must not null out the whole curated payload.
    try:
        curated.quant_fingerprint = build_quant_fingerprint(
            income, balance, cashflow, prof
        ).to_dict()
    except Exception as e:
        logger.warning("[%s] quant fingerprint computation failed: %s", ticker, e)
    return curated


def _build_technical_data(prices: list[dict]) -> list[dict]:
    """Compute SMA 9/20/50/100/200 and RSI(14) from raw OHLCV data.

    Input: list of {date, open, high, low, close, volume} dicts, newest first (FMP order).
    Output: list of dicts oldest first (chronological), each with OHLCV + sma_* + rsi fields.
    """
    if not prices:
        return []

    # Reverse to oldest-first for computation
    rows = list(reversed(prices))
    closes = [float(r.get("close", 0) or 0) for r in rows]
    n = len(closes)

    # ── SMA computation ──────────────────────────────────────────────────
    sma_periods = [9, 20, 50, 100, 200]
    sma_values: dict[int, list[float | None]] = {}
    for period in sma_periods:
        vals: list[float | None] = []
        for i in range(n):
            if i < period - 1:
                vals.append(None)
            else:
                vals.append(round(sum(closes[i - period + 1 : i + 1]) / period, 4))
        sma_values[period] = vals

    # ── RSI(14) computation (Wilder's smoothing) ─────────────────────────
    rsi_period = 14
    rsi_values: list[float | None] = [None] * n
    if n > rsi_period:
        deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
        # Seed: simple average of first 14 deltas
        gains = [max(d, 0) for d in deltas[:rsi_period]]
        losses = [abs(min(d, 0)) for d in deltas[:rsi_period]]
        avg_gain = sum(gains) / rsi_period
        avg_loss = sum(losses) / rsi_period

        if avg_loss == 0:
            rsi_values[rsi_period] = 100.0
        else:
            rsi_values[rsi_period] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

        # Subsequent: exponential smoothing
        for i in range(rsi_period, len(deltas)):
            gain = max(deltas[i], 0)
            loss = abs(min(deltas[i], 0))
            avg_gain = (avg_gain * (rsi_period - 1) + gain) / rsi_period
            avg_loss = (avg_loss * (rsi_period - 1) + loss) / rsi_period
            if avg_loss == 0:
                rsi_values[i + 1] = 100.0
            else:
                rsi_values[i + 1] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    # ── Assemble output ──────────────────────────────────────────────────
    result = []
    for i, row in enumerate(rows):
        result.append({
            "date": row.get("date", ""),
            "open": float(row.get("open", 0) or 0),
            "high": float(row.get("high", 0) or 0),
            "low": float(row.get("low", 0) or 0),
            "close": closes[i],
            "volume": int(row.get("volume", 0) or 0),
            "sma_9": sma_values[9][i],
            "sma_20": sma_values[20][i],
            "sma_50": sma_values[50][i],
            "sma_100": sma_values[100][i],
            "sma_200": sma_values[200][i],
            "rsi": rsi_values[i],
        })
    return result
