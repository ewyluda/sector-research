"""Company-workspace snapshot service.

Slice 1 surfaces only the header (live quote + identity from FMP). Later slices
add /overview, /financials, /transcripts to this module.

Scaling convention: the backend emits fraction-form ratios (0.69 = 69%); the
frontend (formatStat.ts) multiplies by 100 exactly once. Pinned by
backend/tests/test_metric_scaling.py — do not re-litigate.
"""
import asyncio
from datetime import date, timedelta
from typing import Optional

from pydantic import BaseModel

from backend.app.services.metric_guards import gross_corruption, guard_correlated, guard_margin


class CompanyHeader(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    logo_url: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    delay_label: str = "15 min delay"  # static placeholder; FMP /stable does not expose a real-time tier flag


def _as_dict(value: object) -> dict:
    """FMP helpers return dicts, but degrade defensively to {} for [] / None."""
    return value if isinstance(value, dict) else {}


async def build_company_header(fmp, ticker: str) -> CompanyHeader:
    """Assemble the persistent header payload.

    `fmp` is the shared FMPClient (app.state.fmp). Quote feeds price/change;
    profile feeds identity. Missing data degrades to None — the shell never
    needs more than the ticker to render.
    """
    ticker = ticker.upper()

    try:
        quote, _ = await fmp.get_quote(ticker)
    except Exception:
        quote = {}
    try:
        profile, _ = await fmp.get_company_profile(ticker)
    except Exception:
        profile = {}

    quote = _as_dict(quote)
    profile = _as_dict(profile)

    price = quote.get("price")
    if price is None:
        price = profile.get("price")

    return CompanyHeader(
        ticker=ticker,
        name=profile.get("companyName"),
        exchange=profile.get("exchangeShortName"),
        logo_url=profile.get("image"),
        currency=profile.get("currency"),
        price=price,
        change=quote.get("change"),
        # FMP /stable/quote uses "changePercentage" (singular); verified against live API.
        change_pct=quote.get("changePercentage"),
    )


class StatItem(BaseModel):
    label: str
    value: Optional[float] = None
    unit: str  # "pct" | "pct_growth" | "x" | "money" | "num" | "int"


class StatGroup(BaseModel):
    title: str
    items: list[StatItem]


class PricePoint(BaseModel):
    date: str
    close: float


class CompanyOverview(BaseModel):
    ticker: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    stats: list[StatGroup]
    prices: list[PricePoint]


def _f(d: dict, key: str) -> Optional[float]:
    """Safe float read: None if absent or non-numeric."""
    v = d.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _annualize_cumulative(x: Optional[float], years: int) -> Optional[float]:
    """Convert FMP's cumulative multi-year growth to a CAGR for display.

    FMP's fiveY/tenYRevenueGrowthPerShare are CUMULATIVE per-share growth over
    the window, not annual rates (live-verified 2026-06-10: MSFT
    fiveYRevenueGrowthPerShare=1.0168, i.e. revenue/share roughly doubled over
    5y ≈ 15%/yr — 101.7%/yr would be absurd). cagr = (1 + x)^(1/n) - 1;
    x <= -1 (wipeout or garbage) -> None.
    """
    if x is None or x <= -1:
        return None
    return (1 + x) ** (1 / years) - 1


async def _safe_fetch(coro, default):
    """Await an FMP client coroutine, unpacking (data, citation); return `default` on any error."""
    try:
        data, _ = await coro
        return data
    except Exception:
        return default


async def build_company_overview(fmp, ticker: str) -> CompanyOverview:
    """Assemble the Overview-tab payload from five FMP endpoints (fmp-only).

    Valuation ratios + margins come from ratios-ttm; EV multiples + returns
    from key-metrics-ttm; growth/CAGR from financial-growth; identity + market
    cap from profile; 5y daily closes from historical-price. Any missing field
    degrades to None (rendered em-dash).
    """
    ticker = ticker.upper()
    today = date.today()
    five_y_ago = today - timedelta(days=365 * 5 + 2)  # 5y window + 2-day buffer so it opens on a trading day

    profile, km, ratios, growth_list, prices_raw = await asyncio.gather(
        _safe_fetch(fmp.get_company_profile(ticker), {}),
        _safe_fetch(fmp.get_key_metrics_ttm(ticker), {}),
        _safe_fetch(fmp.get_ratios_ttm(ticker), {}),
        _safe_fetch(fmp.get_financial_growth(ticker, period="annual", limit=1), []),
        _safe_fetch(fmp.get_historical_price_adjusted(ticker, five_y_ago.isoformat(), today.isoformat()), []),
    )

    pr = _as_dict(profile)
    km = _as_dict(km)
    ra = _as_dict(ratios)
    fg = growth_list[0] if isinstance(growth_list, list) and growth_list else {}
    fg = _as_dict(fg)

    market_cap = _f(pr, "marketCap")
    if market_cap is None:
        market_cap = _f(km, "marketCap")

    # FMP TTM field names below were verified against the live /stable API
    # (key-metrics-ttm + ratios-ttm). NOTE: these intentionally differ from the
    # keys graph/nodes.py reads (e.g. returnOnEquityTTM here vs roeTTM there);
    # the ratios live on ratios-ttm, not key-metrics-ttm. Do not "align" to nodes.py.
    raw_gross = _f(ra, "grossProfitMarginTTM")
    corrupt = gross_corruption(raw_gross)

    stats = [
        StatGroup(title="Profile", items=[
            StatItem(label="Market Cap", value=market_cap, unit="money"),
            StatItem(label="Enterprise Value", value=_f(km, "enterpriseValueTTM"), unit="money"),
            StatItem(label="Beta", value=_f(pr, "beta"), unit="num"),
            StatItem(label="Employees", value=_f(pr, "fullTimeEmployees"), unit="int"),
        ]),
        StatGroup(title="Margins", items=[
            # guard_margin: gross > 1.0 is impossible → nulled; others warn-only
            # outside [-5.0, 1.5] (see services/metric_guards.py).
            # guard_correlated: when gross is corrupt, EBITDA margin is also poisoned.
            StatItem(label="Gross", value=guard_margin(raw_gross, metric="grossProfitMarginTTM", ticker=ticker), unit="pct"),
            StatItem(label="EBITDA", value=guard_correlated(
                guard_margin(_f(ra, "ebitdaMarginTTM"), metric="ebitdaMarginTTM", ticker=ticker),
                corrupt=corrupt, metric="ebitdaMarginTTM", ticker=ticker,
            ), unit="pct"),
            StatItem(label="Operating", value=guard_margin(_f(ra, "operatingProfitMarginTTM"), metric="operatingProfitMarginTTM", ticker=ticker), unit="pct"),
            StatItem(label="Pre-Tax", value=guard_margin(_f(ra, "pretaxProfitMarginTTM"), metric="pretaxProfitMarginTTM", ticker=ticker), unit="pct"),
            StatItem(label="Net", value=guard_margin(_f(ra, "netProfitMarginTTM"), metric="netProfitMarginTTM", ticker=ticker), unit="pct"),
        ]),
        StatGroup(title="Returns (TTM)", items=[
            StatItem(label="ROE", value=_f(km, "returnOnEquityTTM"), unit="pct"),
            StatItem(label="ROA", value=_f(km, "returnOnAssetsTTM"), unit="pct"),
            StatItem(label="ROIC", value=_f(km, "returnOnInvestedCapitalTTM"), unit="pct"),
            StatItem(label="ROCE", value=_f(km, "returnOnCapitalEmployedTTM"), unit="pct"),
            StatItem(label="ROTA", value=_f(km, "returnOnTangibleAssetsTTM"), unit="pct"),
        ]),
        StatGroup(title="Valuation (TTM)", items=[
            StatItem(label="P/E", value=_f(ra, "priceToEarningsRatioTTM"), unit="x"),
            StatItem(label="P/B", value=_f(ra, "priceToBookRatioTTM"), unit="x"),
            StatItem(label="P/S", value=_f(ra, "priceToSalesRatioTTM"), unit="x"),
            StatItem(label="P/FCF", value=_f(ra, "priceToFreeCashFlowRatioTTM"), unit="x"),
            StatItem(label="EV/EBITDA", value=guard_correlated(
                _f(km, "evToEBITDATTM"), corrupt=corrupt, metric="evToEBITDATTM", ticker=ticker,
            ), unit="x"),
            StatItem(label="EV/Sales", value=_f(km, "evToSalesTTM"), unit="x"),
            StatItem(label="PEG", value=_f(ra, "priceToEarningsGrowthRatioTTM"), unit="x"),
        ]),
        StatGroup(title="Valuation (Forward)", items=[
            StatItem(label="Fwd PEG", value=_f(ra, "forwardPriceToEarningsGrowthRatioTTM"), unit="x"),
            StatItem(label="Price/Fair Value", value=_f(ra, "priceToFairValueTTM"), unit="x"),
            StatItem(label="Earnings Yield", value=_f(km, "earningsYieldTTM"), unit="pct"),
            StatItem(label="FCF Yield", value=_f(km, "freeCashFlowYieldTTM"), unit="pct"),
        ]),
        StatGroup(title="Financial Health", items=[
            StatItem(label="Current Ratio", value=_f(km, "currentRatioTTM"), unit="x"),
            StatItem(label="Net Debt/EBITDA", value=guard_correlated(
                _f(km, "netDebtToEBITDATTM"), corrupt=corrupt, metric="netDebtToEBITDATTM", ticker=ticker,
            ), unit="x"),
            StatItem(label="Cash/Share", value=_f(ra, "cashPerShareTTM"), unit="money"),
            StatItem(label="Working Capital", value=_f(km, "workingCapitalTTM"), unit="money"),
        ]),
        StatGroup(title="Growth", items=[
            # "pct_growth" tells the frontend these are growth rates: tiny-base
            # artifacts (|value| > 10, i.e. beyond ±1000%) render as "n/m".
            StatItem(label="Revenue", value=_f(fg, "revenueGrowth"), unit="pct_growth"),
            StatItem(label="EPS", value=_f(fg, "epsgrowth"), unit="pct_growth"),
            StatItem(label="FCF", value=_f(fg, "freeCashFlowGrowth"), unit="pct_growth"),
            StatItem(label="EBITDA", value=_f(fg, "ebitdaGrowth"), unit="pct_growth"),
            # FMP's five/tenYRevenueGrowthPerShare are CUMULATIVE per-share
            # growth over the window — annualize so the "CAGR" labels are true.
            StatItem(label="Rev 5Y CAGR", value=_annualize_cumulative(_f(fg, "fiveYRevenueGrowthPerShare"), 5), unit="pct_growth"),
            StatItem(label="Rev 10Y CAGR", value=_annualize_cumulative(_f(fg, "tenYRevenueGrowthPerShare"), 10), unit="pct_growth"),
        ]),
        StatGroup(title="Dividends", items=[
            StatItem(label="Yield", value=_f(ra, "dividendYieldTTM"), unit="pct"),
            StatItem(label="Payout", value=_f(ra, "dividendPayoutRatioTTM"), unit="pct"),
            StatItem(label="DPS", value=_f(ra, "dividendPerShareTTM"), unit="money"),
            # cumulative like its revenue siblings; label says "Growth" not "CAGR", so left unannualized deliberately
            StatItem(label="DPS 5Y Growth", value=_f(fg, "fiveYDividendperShareGrowthPerShare"), unit="pct_growth"),
        ]),
    ]

    prices: list[PricePoint] = []
    if isinstance(prices_raw, list):
        for row in prices_raw:
            if isinstance(row, dict) and row.get("date") and isinstance(row.get("adjClose"), (int, float)):
                prices.append(PricePoint(date=row["date"], close=float(row["adjClose"])))
        prices.sort(key=lambda p: p.date)  # FMP returns newest-first; chart wants oldest-first

    return CompanyOverview(
        ticker=ticker,
        sector=pr.get("sector"),
        industry=pr.get("industry"),
        stats=stats,
        prices=prices,
    )


class CompanyFinancials(BaseModel):
    ticker: str
    period: str
    periods: list[str]
    income: dict[str, list[Optional[float]]]
    balance: dict[str, list[Optional[float]]]
    cashflow: dict[str, list[Optional[float]]]


def _period_label(row: dict, period: str) -> str:
    fy = row.get("fiscalYear")
    if fy is None:
        fy = str(row.get("date", ""))[:4]
    if period == "annual":
        return str(fy)
    p = row.get("period", "")
    return f"{p} {fy}".strip()


def _columnize(rows: list, n: int) -> dict[str, list[Optional[float]]]:
    """Reshape up to n statement rows (newest-first) into {key: [values]} columns,
    aligned by index, numeric values only (bool excluded). Trailing slots are None
    when a statement returns fewer periods than the income statement."""
    out: dict[str, list[Optional[float]]] = {}
    for i in range(min(n, len(rows))):
        row = rows[i]
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out.setdefault(k, [None] * n)[i] = float(v)
    return out


async def build_company_financials(
    fmp, ticker: str, period: str = "quarter", limit: int = 12
) -> CompanyFinancials:
    """Reshape the three FMP statements into period-aligned column dicts (fmp-only).

    Periods are derived from the income statement (newest-first, as FMP returns);
    balance sheet and cash flow are aligned to those periods by index. Only numeric
    fields are kept. The frontend row-spec selects/orders/labels the keys.
    """
    ticker = ticker.upper()
    inc, bal, cf = await asyncio.gather(
        _safe_fetch(fmp.get_income_statement(ticker, period=period, limit=limit), []),
        _safe_fetch(fmp.get_balance_sheet(ticker, period=period, limit=limit), []),
        _safe_fetch(fmp.get_cash_flow(ticker, period=period, limit=limit), []),
    )
    inc = inc if isinstance(inc, list) else []
    bal = bal if isinstance(bal, list) else []
    cf = cf if isinstance(cf, list) else []

    periods = [_period_label(r, period) for r in inc if isinstance(r, dict)]
    n = len(periods)

    return CompanyFinancials(
        ticker=ticker,
        period=period,
        periods=periods,
        income=_columnize(inc, n),
        balance=_columnize(bal, n),
        cashflow=_columnize(cf, n),
    )
