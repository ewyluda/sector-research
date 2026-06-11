"""Identity test for _fmt_fundamentals refactor (M3.6).

Strategy: _fmt_fundamentals_legacy is a verbatim copy of the pre-refactor
function pasted into this test file only.  We assert new == legacy across
three representative fixture payloads:
  1. Full-data payload (income, balance, cashflow, profile, dcf, estimates,
     fin_growth, valuation ratios, consensus, ratings, grades, insider).
  2. Sparse/missing-fields payload (profile only, all optional args absent).
  3. Empty payload (all empty / None).

This is stronger than hardcoded golden strings because it exercises arbitrary
field combinations without enumerating every rendered character manually.
"""
import unittest
from typing import Any

# ── Legacy copy (verbatim from formatters.py pre-refactor) ────────────────────

def _fmt_fundamentals_legacy(
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
) -> str:
    def _fv(val: Any, divisor: float = 1e9, suffix: str = "B") -> str:
        if val is None or val == 0:
            return "N/A"
        return f"${val / divisor:.2f}{suffix}"

    def _pct(a: float | None, b: float | None) -> str:
        if a is None or b is None or b == 0:
            return "N/A"
        return f"{(a - b) / abs(b) * 100:+.1f}%"

    def _first_metric(*candidates):
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

    parts: list[str] = []

    if profile and isinstance(profile, dict):
        parts.append(f"Company: {profile.get('companyName', ticker)}")
        parts.append(f"Sector: {profile.get('sector')} | Industry: {profile.get('industry')}")
        parts.append(f"Market Cap: ${profile.get('marketCap', 0)/1e9:.1f}B")
        parts.append(f"Beta: {profile.get('beta', 'N/A')}")
        parts.append(f"Description: {str(profile.get('description', ''))[:300]}")

    rt = ratios if isinstance(ratios, dict) else {}
    km = key_metrics if isinstance(key_metrics, dict) else {}
    if rt or km:
        parts.append("\nValuation Ratios (TTM):")
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

    if income:
        parts.append(f"\nQuarterly Income Statement ({len(income)} quarters, newest first):")
        for i, stmt in enumerate(income[:8]):
            rev = stmt.get("revenue", 0) or 0
            gp = stmt.get("grossProfit", 0) or 0
            oi = stmt.get("operatingIncome", 0) or 0
            ni = stmt.get("netIncome", 0) or 0
            eps = stmt.get("eps", "N/A")
            gm = f"{gp/rev*100:.1f}%" if rev else "N/A"
            om = f"{oi/rev*100:.1f}%" if rev else "N/A"
            nm = f"{ni/rev*100:.1f}%" if rev else "N/A"
            yoy = ""
            if i + 4 < len(income):
                prev_rev = income[i + 4].get("revenue", 0) or 0
                if prev_rev:
                    yoy = f" (YoY: {(rev - prev_rev)/abs(prev_rev)*100:+.1f}%)"
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            parts.append(f"  {period}: Rev {_fv(rev)} {yoy} | GM {gm} | OM {om} | NM {nm} | EPS {eps}")

    if balance:
        parts.append(f"\nBalance Sheet ({len(balance)} quarters, newest first):")
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
        if income:
            ie = income[0].get("interestExpense", 0) or 0
            if ie:
                parts.append(f"  Latest Interest Expense: {_fv(abs(ie))}")

    if cashflow:
        parts.append(f"\nCash Flow ({len(cashflow)} quarters, newest first):")
        for stmt in cashflow[:4]:
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            ocf = stmt.get("operatingCashFlow", 0) or 0
            fcf = stmt.get("freeCashFlow", 0) or 0
            capex = stmt.get("capitalExpenditure", 0) or 0
            sbc = stmt.get("stockBasedCompensation", 0) or 0
            parts.append(f"  {period}: OCF {_fv(ocf)} | FCF {_fv(fcf)} | CapEx {_fv(capex)} | SBC {_fv(sbc)}")

    if dcf and isinstance(dcf, dict):
        dcf_val = dcf.get("dcf")
        stock_price = dcf.get("Stock Price") or dcf.get("stockPrice")
        if dcf_val:
            gap = ""
            if stock_price and float(stock_price) > 0:
                gap_pct = (float(dcf_val) - float(stock_price)) / float(stock_price) * 100
                gap = f" ({gap_pct:+.1f}% vs current)"
            parts.append(f"\nDCF Intrinsic Value: ${dcf_val}{gap}")

    if estimates:
        parts.append(f"\nAnalyst Estimates ({len(estimates)} quarters):")
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

    if fin_growth:
        parts.append(f"\nGrowth Rates ({len(fin_growth)} quarters):")
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

    if grade_consensus or price_target or ratings_snap:
        parts.append("\nAnalyst Consensus & Ratings:")
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

    if isinstance(grades_recent, list) and grades_recent:
        parts.append(f"\nRecent Analyst Actions ({len(grades_recent[:8])} most recent):")
        for g in grades_recent[:8]:
            date_ = g.get("date", "")[:10]
            firm = g.get("gradingCompany") or "Unknown"
            prev = g.get("previousGrade") or "—"
            new = g.get("newGrade") or "—"
            action = g.get("action") or ""
            parts.append(f"  {date_} {firm}: {prev} → {new} ({action})")

    if isinstance(grades_hist, list) and grades_hist:
        parts.append("\nAnalyst Consensus Trend (monthly):")
        for row in grades_hist[:4]:
            date_ = row.get("date", "")[:7]
            sb = row.get("analystRatingsStrongBuy") or 0
            b = row.get("analystRatingsBuy") or 0
            h = row.get("analystRatingsHold") or 0
            s = row.get("analystRatingsSell") or 0
            ss = row.get("analystRatingsStrongSell") or 0
            parts.append(f"  {date_}: SB {sb} / B {b} / H {h} / S {s} / SS {ss}")

    if isinstance(insider_tx, list) and insider_tx:
        meaningful = [
            t for t in insider_tx
            if float(t.get("securitiesTransacted") or 0) > 0
            and float(t.get("price") or 0) > 0
        ]
        if meaningful:
            buys = sum(
                float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
                for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "A"
            )
            sells = sum(
                float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
                for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "D"
            )
            parts.append(f"\nInsider Transactions (last {len(meaningful)} Form 4 filings):")
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

    return "\n".join(parts)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_LIVE_KM = {
    "symbol": "NVDA",
    "returnOnEquityTTM": 1.07,
    "returnOnInvestedCapitalTTM": 0.78,
    "returnOnAssetsTTM": 0.65,
    "returnOnTangibleAssetsTTM": 0.66,
    "evToEBITDATTM": 42.0,
    "marketCap": 3.5e12,
}
_LIVE_RATIOS = {
    "symbol": "NVDA",
    "priceToEarningsRatioTTM": 51.2,
    "enterpriseValueMultipleTTM": 44.7,
    "priceToBookRatioTTM": 38.1,
    "priceToFreeCashFlowRatioTTM": 60.3,
    "priceToSalesRatioTTM": 26.4,
    "priceToEarningsGrowthRatioTTM": 1.8,
    "dividendYieldTTM": 0.0003,
    "interestCoverageRatioTTM": 341.2,
}
_INCOME = [
    {"period": "Q1", "calendarYear": "2024", "revenue": 26e9, "grossProfit": 18e9,
     "operatingIncome": 15e9, "netIncome": 14e9, "eps": 0.57, "interestExpense": -500e6},
    {"period": "Q4", "calendarYear": "2023", "revenue": 22e9, "grossProfit": 15e9,
     "operatingIncome": 12e9, "netIncome": 11e9, "eps": 0.45},
]
_BALANCE = [
    {"period": "Q1", "calendarYear": "2024", "cashAndCashEquivalents": 7e9,
     "shortTermDebt": 1e9, "longTermDebt": 8e9, "totalDebt": 9e9,
     "totalEquity": 40e9, "totalCurrentAssets": 20e9, "totalCurrentLiabilities": 8e9},
]
_CASHFLOW = [
    {"period": "Q1", "calendarYear": "2024", "operatingCashFlow": 15e9,
     "freeCashFlow": 14e9, "capitalExpenditure": -1e9, "stockBasedCompensation": 1e9},
]
_PROFILE = {
    "companyName": "NVIDIA Corp", "sector": "Technology", "industry": "Semiconductors",
    "marketCap": 3.5e12, "beta": 1.7, "description": "NVIDIA designs GPUs.", "price": 880.0,
}
_DCF = {"dcf": 950.0, "Stock Price": 880.0}
_ESTIMATES = [
    {"date": "2024-07-01", "estimatedRevenueAvg": 28e9, "estimatedEpsAvg": 0.63,
     "actualRevenue": 30e9, "actualEps": 0.68},
]
_FIN_GROWTH = [
    {"date": "2024-07-01", "revenueGrowth": 0.22, "epsgrowth": 0.35, "freeCashFlowGrowth": 0.28},
]
_GRADE_CONSENSUS = {
    "strongBuy": 20, "buy": 10, "hold": 5, "sell": 1, "strongSell": 0, "consensus": "Strong Buy",
}
_PRICE_TARGET = {
    "targetConsensus": 950.0, "targetHigh": 1100.0, "targetLow": 800.0, "targetMedian": 940.0,
}
_RATINGS_SNAP = {"rating": "S", "overallScore": 5}
_GRADES_RECENT = [
    {"date": "2024-03-01", "gradingCompany": "Goldman", "previousGrade": "Neutral",
     "newGrade": "Buy", "action": "upgrade"},
]
_GRADES_HIST = [
    {"date": "2024-03", "analystRatingsStrongBuy": 18, "analystRatingsBuy": 8,
     "analystRatingsHold": 3, "analystRatingsSell": 1, "analystRatingsStrongSell": 0},
]
_INSIDER_TX = [
    {"filingDate": "2024-02-15", "reportingName": "Jensen Huang", "typeOfOwner": "CEO",
     "securitiesTransacted": 100000, "price": 750.0, "acquisitionOrDisposition": "D"},
    {"filingDate": "2024-01-10", "reportingName": "CFO Name", "typeOfOwner": "CFO",
     "securitiesTransacted": 5000, "price": 700.0, "acquisitionOrDisposition": "A"},
]


def _call_new(*args, **kwargs) -> str:
    from backend.app.graph.formatters import _fmt_fundamentals
    return _fmt_fundamentals(*args, **kwargs)


class TestFmtFundamentalsIdentity(unittest.TestCase):
    """New per-section composer must produce byte-identical output to the
    pre-refactor monolith across all three fixture variants."""

    def test_full_data_payload_identity(self):
        kwargs = dict(
            dcf=_DCF,
            estimates=_ESTIMATES,
            key_metrics=_LIVE_KM,
            ratios=_LIVE_RATIOS,
            fin_growth=_FIN_GROWTH,
            grade_consensus=_GRADE_CONSENSUS,
            price_target=_PRICE_TARGET,
            ratings_snap=_RATINGS_SNAP,
            grades_recent=_GRADES_RECENT,
            grades_hist=_GRADES_HIST,
            insider_tx=_INSIDER_TX,
        )
        legacy = _fmt_fundamentals_legacy(
            "NVDA", _INCOME, _BALANCE, _CASHFLOW, _PROFILE, **kwargs
        )
        new = _call_new(
            "NVDA", _INCOME, _BALANCE, _CASHFLOW, _PROFILE, **kwargs
        )
        self.assertEqual(new, legacy)

    def test_sparse_payload_identity(self):
        """Profile only, all optional kwargs absent — exercises the guard
        clauses at the top of each section helper."""
        profile = {
            "companyName": "Apple", "sector": "Tech",
            "industry": "Consumer Electronics", "marketCap": 3e12,
            "beta": 1.2, "description": "Makes iPhones.", "price": 200.0,
        }
        legacy = _fmt_fundamentals_legacy("AAPL", [], [], [], profile)
        new = _call_new("AAPL", [], [], [], profile)
        self.assertEqual(new, legacy)

    def test_empty_payload_identity(self):
        """All empty — should return empty string."""
        legacy = _fmt_fundamentals_legacy("X", [], [], [], {})
        new = _call_new("X", [], [], [], {})
        self.assertEqual(new, legacy)
        self.assertEqual(new, "")


if __name__ == "__main__":
    unittest.main()
