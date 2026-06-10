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
        self.assertTrue(by_key["roa_positive"]["passed"])
        self.assertTrue(by_key["cfo_positive"]["passed"])
        self.assertTrue(by_key["accruals_quality"]["passed"])


class AltmanZTests(unittest.TestCase):
    """Hand-computed: A=(200-100)/400=.25, B=120/400=.3, C=120/400=.3,
    D=2000/180=11.1111, E=400/400=1.0
    Z = 1.2(.25)+1.4(.3)+3.3(.3)+0.6(11.1111)+1.0 = 9.3767 -> safe."""

    def test_z_value_and_zone(self):
        a = fingerprint()["altman_z"]
        self.assertAlmostEqual(a["z"], 9.3767, places=3)
        self.assertEqual(a["zone"], "safe")
        self.assertIsNone(a["not_applicable_reason"])

    def test_zones(self):
        # Shrink market cap so D collapses: mcap=100 -> D=0.5556, 0.6D=0.3333
        # Z = .3+.42+.99+.3333+1.0 = 3.0433 -> still safe (>2.99).
        a = fingerprint(profile={"marketCap": 100, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "safe")
        # mcap=50 -> 0.6D=0.1667, Z=2.8767 -> grey
        a = fingerprint(profile={"marketCap": 50, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "grey")
        # mcap=1 + gut EBIT/revenue via zero-revenue income would null Z;
        # instead drop retained earnings & ebit through balance/income edits:
        income = [_iq(100, 60, 20, -200, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
        a = fingerprint(income=income, profile={"marketCap": 1, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "distress")

    def test_financial_sector_not_applicable(self):
        a = fingerprint(profile={"marketCap": 2000, "sector": "Financial Services"})["altman_z"]
        self.assertIsNone(a["z"])
        self.assertIsNone(a["zone"])
        self.assertIn("financial", a["not_applicable_reason"].lower())

    def test_missing_inputs_null_z_without_reason(self):
        bal = [{k: v for k, v in b.items() if k != "retainedEarnings"} for b in BALANCE]
        a = fingerprint(balance=bal)["altman_z"]
        self.assertIsNone(a["z"])
        self.assertIsNone(a["not_applicable_reason"])

    def test_mktcap_legacy_fallback(self):
        a = fingerprint(profile={"mktCap": 2000, "sector": "Technology"})["altman_z"]
        self.assertAlmostEqual(a["z"], 9.3767, places=3)


class AltmanZEbitFallbackTests(unittest.TestCase):
    def test_ebit_fallback_to_operating_income(self):
        income = [{k: v for k, v in q.items() if k != "ebit"} for q in INCOME]
        a = fingerprint(income=income)["altman_z"]
        # operatingIncome == ebit in the fixture, so Z is unchanged
        self.assertAlmostEqual(a["z"], 9.3767, places=3)


class BeneishMTests(unittest.TestCase):
    """Hand-computed ratios for the fixture:
    DSRI=(40/400)/(45/360)=0.8        GMI=(200/360)/(240/400)=0.9259
    AQI=(1-320/400)/(1-295/380)=0.8941  SGI=400/360=1.1111
    DEPI=(20/115)/(20/120)=1.0435     SGAI=(40/400)/(40/360)=0.9
    LVGI=(150/400)/(160/380)=0.8906   TATA=(80-120)/400=-0.1
    M = -4.84 + .92(.8)+.528(.9259)+.404(.8941)+.892(1.1111)
        +.115(1.0435)-.172(.9)+4.679(-.1)-.327(.8906) = -3.0567 -> unlikely"""

    def test_m_value_zone_and_ratios(self):
        b = fingerprint()["beneish_m"]
        self.assertAlmostEqual(b["m"], -3.0567, places=3)
        self.assertEqual(b["zone"], "unlikely")
        self.assertEqual(b["inputs_missing"], [])
        self.assertAlmostEqual(b["ratios"]["dsri"], 0.8, places=4)
        self.assertAlmostEqual(b["ratios"]["tata"], -0.1, places=4)
        self.assertAlmostEqual(b["ratios"]["lvgi"], 0.8906, places=3)

    def test_missing_sga_nulls_m_with_reason(self):
        income = [{k: v for k, v in q.items()
                   if k != "sellingGeneralAndAdministrativeExpenses"} for q in INCOME]
        b = fingerprint(income=income)["beneish_m"]
        self.assertIsNone(b["m"])
        self.assertIsNone(b["zone"])
        self.assertIn("sgai", b["inputs_missing"])

    def test_four_quarters_nulls_m(self):
        b = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["beneish_m"]
        self.assertIsNone(b["m"])
        # TATA is current-window-only and stays computable.
        self.assertNotIn("tata", b["inputs_missing"])
        self.assertIn("dsri", b["inputs_missing"])

    def test_financial_sector_not_applicable(self):
        b = fingerprint(profile={"marketCap": 2000, "sector": "Financial Services"})["beneish_m"]
        self.assertIsNone(b["m"])
        self.assertIsNone(b["zone"])
        self.assertIn("financial", b["not_applicable_reason"].lower())

    def test_caution_and_flag_zones(self):
        # TATA is the lever: M = -3.0567 + 4.679*(tata + 0.1).
        # CFO 10/q -> TATA (80-40)/400 = 0.1 -> M ≈ -2.1209 -> caution
        caution_cf = [_cq(10, 25, 5, 4, 20)] * 4 + [_cq(20, 18, 5, 3, 15)] * 4
        b = fingerprint(cashflow=caution_cf)["beneish_m"]
        self.assertEqual(b["zone"], "caution")
        # CFO 0/q -> TATA 80/400 = 0.2 -> M ≈ -1.6530 -> flag
        flag_cf = [_cq(0, 25, 5, 4, 20)] * 4 + [_cq(20, 18, 5, 3, 15)] * 4
        b = fingerprint(cashflow=flag_cf)["beneish_m"]
        self.assertEqual(b["zone"], "flag")

    def test_negative_total_assets_nulls_balance_ratios(self):
        bal = [dict(BALANCE[0], totalAssets=-400)] + [dict(b) for b in BALANCE[1:]]
        b = fingerprint(balance=bal)["beneish_m"]
        self.assertIsNone(b["m"])
        self.assertIn("aqi", b["inputs_missing"])
        self.assertIn("lvgi", b["inputs_missing"])


class ScalarMetricTests(unittest.TestCase):
    def test_accruals_ratio_avg_ta(self):
        # (80-120)/((400+380)/2) = -40/390 = -0.1026
        self.assertAlmostEqual(fingerprint()["accruals_ratio"], -0.1026, places=3)

    def test_accruals_falls_back_to_ta0_with_four_quarters(self):
        fp = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])
        self.assertAlmostEqual(fp["accruals_ratio"], -0.1, places=4)  # -40/400

    def test_fcf_conversion(self):
        self.assertAlmostEqual(fingerprint()["fcf_conversion"], 1.25, places=4)  # 100/80

    def test_fcf_conversion_null_on_negative_ni(self):
        income = [_iq(100, 60, -20, 30, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
        self.assertIsNone(fingerprint(income=income)["fcf_conversion"])

    def test_sbc_block(self):
        sbc = fingerprint()["sbc"]
        self.assertAlmostEqual(sbc["sbc_pct_revenue"], 4.0, places=2)        # 16/400
        self.assertAlmostEqual(sbc["share_growth_yoy_pct"], 2.0, places=2)   # 102/100 - 1

    def test_sbc_share_growth_null_with_four_quarters(self):
        sbc = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["sbc"]
        self.assertAlmostEqual(sbc["sbc_pct_revenue"], 4.0, places=2)
        self.assertIsNone(sbc["share_growth_yoy_pct"])


class MarginSlopeTests(unittest.TestCase):
    def test_rising_gross_margin_positive_slope(self):
        # Chronological gross margins: 4x 55.56% then 4x 60% -> positive slope.
        slopes = fingerprint()["margin_slopes"]
        self.assertGreater(slopes["gross"]["slope_pp_per_quarter"], 0)
        self.assertEqual(slopes["gross"]["quarters"], 8)
        self.assertIn("operating", slopes)
        self.assertIn("net", slopes)

    def test_skips_zero_revenue_quarters(self):
        income = list(INCOME)
        income[7] = dict(income[7], revenue=0)
        slopes = fingerprint(income=income)["margin_slopes"]
        self.assertEqual(slopes["gross"]["quarters"], 7)

    def test_under_four_points_null_slope(self):
        slopes = fingerprint(INCOME[:3], BALANCE[:3], CASHFLOW[:3])["margin_slopes"]
        self.assertIsNone(slopes["gross"]["slope_pp_per_quarter"])
        self.assertEqual(slopes["gross"]["quarters"], 3)


if __name__ == "__main__":
    unittest.main()
