"""Peer comparison schemas — shared by the peers API, /compare, and the
workspace differentiation step.

Moved out of workspace_schemas.py (2026-06-09) so the product surface and
the workspace step share one source of truth. workspace_schemas re-exports
these names for backward compatibility — old persisted step_outputs JSONB
(without the post-move optional fields) still validates because every new
field defaults to None.

Margin / growth / return values are ratios (0.46 = 46%), matching the FMP
wire format. market_cap is absolute USD.
"""
from pydantic import BaseModel, Field


class PeerCompRow(BaseModel):
    """A single row in the peer comparison table."""

    ticker: str = Field(
        description="The peer ticker (or focus ticker for the highlighted row)."
    )
    # Valuation
    pe: float | None = Field(default=None, description="Price-to-earnings.")
    ev_ebitda: float | None = Field(default=None, description="EV/EBITDA.")
    p_b: float | None = Field(default=None, description="Price-to-book.")
    p_fcf: float | None = Field(default=None, description="Price-to-FCF.")
    p_s: float | None = Field(default=None, description="Price-to-sales.")
    peg: float | None = Field(default=None, description="PEG ratio.")
    # Growth
    revenue_yoy: float | None = Field(
        default=None, description="Revenue YoY growth %."
    )
    eps_yoy: float | None = Field(
        default=None, description="EPS YoY growth %."
    )
    # Margins
    gross_margin: float | None = Field(
        default=None, description="Gross margin %."
    )
    operating_margin: float | None = Field(
        default=None, description="Operating margin %."
    )
    ebitda_margin: float | None = Field(
        default=None, description="EBITDA margin %."
    )
    fcf_margin: float | None = Field(
        default=None, description="Free-cash-flow margin %."
    )
    # Returns
    roe: float | None = Field(default=None, description="Return on equity.")
    roic: float | None = Field(
        default=None, description="Return on invested capital."
    )
    roa: float | None = Field(
        default=None, description="Return on (tangible) assets."
    )
    # Context
    market_cap: float | None = Field(
        default=None, description="Market capitalization, USD."
    )


class PeerCompTable(BaseModel):
    """The full peer comparison table."""

    focus_ticker: str = Field(description="Focus company ticker.")
    rows: list[PeerCompRow] = Field(
        default_factory=list, description="Peer rows (focus row first)."
    )
    median: PeerCompRow = Field(
        description="Computed peer median (focus excluded)."
    )
    delta_vs_median_pct: PeerCompRow = Field(
        description="Focus row deltas vs. median (all metrics in %)."
    )


class PeerError(BaseModel):
    """Error during peer resolution or data fetch."""

    peer_ticker: str = Field(description="Peer ticker that failed.")
    error_message: str = Field(description="Error detail.")
