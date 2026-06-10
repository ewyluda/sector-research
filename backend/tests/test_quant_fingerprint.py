"""Deterministic quant fingerprint — pure-math tests on synthetic fixtures.

Fixture design: the 4 current-TTM quarters are identical, the 4 prior-TTM
quarters are identical, so every TTM aggregate is 4x a round number and all
expected values below are hand-computable. Statements are NEWEST FIRST
(FMP order). Hand-computed expectations:

  TTM:   rev=400 gp=240 ni=80 ebit=120 sga=40 cfo=120 fcf=100 da=20 sbc=16 shares(avg)=102
  Prior: rev=360 gp=200 ni=60 ebit=100 sga=40 cfo=80          da=20        shares(avg)=100
  Balance[0]: ta=400 ca=200 cl=100 ltd=50 re=120 rec=40 ppe=100 lti=20 tl=180
  Balance[4]: ta=380 ca=180 cl=100 ltd=60 re=100 rec=45 ppe=95  lti=20 tl=190
  Profile: marketCap=2000, sector=Technology
"""
import unittest

from backend.app.services.quant_fingerprint import (
    _div,
    _ols_slope,
    _ttm,
    _prior_ttm,
    build_quant_fingerprint,
)


def _iq(rev, gp, ni, ebit, sga, shares, op_inc=None):
    return {
        "revenue": rev,
        "grossProfit": gp,
        "netIncome": ni,
        "ebit": ebit,
        "sellingGeneralAndAdministrativeExpenses": sga,
        "weightedAverageShsOutDil": shares,
        "operatingIncome": op_inc if op_inc is not None else ebit,
    }


def _bq(ta, ca, cl, ltd, re, rec, ppe, lti, tl):
    return {
        "totalAssets": ta,
        "totalCurrentAssets": ca,
        "totalCurrentLiabilities": cl,
        "longTermDebt": ltd,
        "retainedEarnings": re,
        "netReceivables": rec,
        "propertyPlantEquipmentNet": ppe,
        "longTermInvestments": lti,
        "totalLiabilities": tl,
    }


def _cq(cfo, fcf, da, sbc, ni):
    return {
        "operatingCashFlow": cfo,
        "freeCashFlow": fcf,
        "depreciationAndAmortization": da,
        "stockBasedCompensation": sbc,
        "netIncome": ni,
    }


# Newest first: 4 current quarters then 4 prior quarters.
INCOME = [_iq(100, 60, 20, 30, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
BALANCE = [_bq(400, 200, 100, 50, 120, 40, 100, 20, 180)] * 4 + \
          [_bq(380, 180, 100, 60, 100, 45, 95, 20, 190)] * 4
CASHFLOW = [_cq(30, 25, 5, 4, 20)] * 4 + [_cq(20, 18, 5, 3, 15)] * 4
PROFILE = {"marketCap": 2000, "sector": "Technology"}


def fingerprint(income=INCOME, balance=BALANCE, cashflow=CASHFLOW, profile=PROFILE):
    return build_quant_fingerprint(income, balance, cashflow, profile).to_dict()


class HelperTests(unittest.TestCase):
    def test_ttm_sums_first_four_quarters(self):
        self.assertEqual(_ttm(INCOME, "revenue"), 400)
        self.assertEqual(_prior_ttm(INCOME, "revenue"), 360)

    def test_ttm_none_when_any_quarter_missing_key(self):
        broken = [dict(q) for q in INCOME]
        del broken[2]["revenue"]
        self.assertIsNone(_ttm(broken, "revenue"))
        self.assertEqual(_prior_ttm(broken, "revenue"), 360)

    def test_ttm_none_when_window_short(self):
        self.assertIsNone(_ttm(INCOME[:3], "revenue"))
        self.assertIsNone(_prior_ttm(INCOME[:6], "revenue"))

    def test_div_guards_none_and_zero(self):
        self.assertIsNone(_div(1.0, 0))
        self.assertIsNone(_div(None, 2.0))
        self.assertIsNone(_div(1.0, None))
        self.assertEqual(_div(1.0, 2.0), 0.5)

    def test_ols_slope_linear_series(self):
        self.assertAlmostEqual(_ols_slope([1.0, 2.0, 3.0, 4.0]), 1.0)
        self.assertAlmostEqual(_ols_slope([4.0, 3.0, 2.0, 1.0]), -1.0)

    def test_ols_slope_needs_four_points(self):
        self.assertIsNone(_ols_slope([1.0, 2.0, 3.0]))


class MetaTests(unittest.TestCase):
    def test_meta_block(self):
        meta = fingerprint()["meta"]
        self.assertEqual(meta["quarters_available"], 8)
        self.assertEqual(meta["basis"], "ttm_vs_prior_ttm")
        self.assertEqual(meta["sector"], "Technology")

    def test_to_dict_is_json_safe(self):
        import json
        json.dumps(fingerprint())  # must not raise


class PiotroskiTests(unittest.TestCase):
    """Fixture passes 8 of 9 checks. no_dilution fails: avg diluted shares
    rose 100 -> 102. Hand-checks: ROA .2 > .1579; CFO 120 > NI 80;
    leverage .125 <= .1579; CR 2.0 > 1.8; GM .6 > .5556; ATO 1.0 > .9474."""

    def test_score_and_evaluated(self):
        p = fingerprint()["piotroski"]
        self.assertEqual(p["score"], 8)
        self.assertEqual(p["components_evaluated"], 9)

    def test_component_keys_and_failure(self):
        p = fingerprint()["piotroski"]
        by_key = {c["key"]: c for c in p["components"]}
        self.assertEqual(
            list(by_key),
            ["roa_positive", "cfo_positive", "roa_delta", "accruals_quality",
             "leverage_delta", "current_ratio_delta", "no_dilution",
             "gross_margin_delta", "asset_turnover_delta"],
        )
        self.assertFalse(by_key["no_dilution"]["passed"])
        self.assertTrue(by_key["roa_positive"]["passed"])
        self.assertTrue(by_key["leverage_delta"]["passed"])

    def test_zero_debt_stays_zero_passes_leverage(self):
        bal = [dict(b, longTermDebt=0) for b in BALANCE]
        p = fingerprint(balance=bal)["piotroski"]
        by_key = {c["key"]: c for c in p["components"]}
        self.assertTrue(by_key["leverage_delta"]["passed"])

    def test_four_quarters_degrades_to_three_evaluated(self):
        p = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["piotroski"]
        self.assertEqual(p["components_evaluated"], 3)
        self.assertEqual(p["score"], 3)  # roa_positive, cfo_positive, accruals_quality
        by_key = {c["key"]: c for c in p["components"]}
        self.assertIsNone(by_key["roa_delta"]["passed"])
        self.assertIsNone(by_key["no_dilution"]["passed"])


if __name__ == "__main__":
    unittest.main()
