"""Business case arithmetic: annualisation, break-even and sensitivity directions."""
from gridsetu.economics import ASSUMPTIONS, annual, sensitivity

WEEKLY = {wk: {"baseline": {"unserved_kwh": u, "import_kwh": 20000.0, "energy_cost_inr": 90000.0,
                            "battery_discharge_kwh": 0.0},
               "gridsetu": {"unserved_kwh": u / 5, "import_kwh": 20500.0, "energy_cost_inr": 93000.0,
                            "battery_discharge_kwh": 900.0}}
          for wk, u in (("stress", 2000.0), ("representative", 300.0))}


def test_annual_break_even_is_cost_over_outage_avoided():
    a = annual(WEEKLY, ASSUMPTIONS)
    d_u = 13 * (2000 - 400) + 39 * (300 - 60)
    d_e = 52 * 3000
    assert a["unserved_avoided_kwh_per_year"] == round(d_u)
    assert a["extra_energy_cost_inr_per_year"] == d_e
    assert abs(a["breakeven_value_inr_per_kwh"] - (a["total_cost_inr_per_year"] + d_e) / d_u) < 0.01
    # battery: 2.3 lakh/MW/month x 0.1 MW x 12 x premium 2
    assert a["costs_inr_per_year"]["battery"] == round(2.3e5 * 0.1 * 12 * 2)
    # at the break-even value the benefit-cost ratio is 1
    at = a["breakeven_value_inr_per_kwh"]
    assert abs(d_u * at / (a["total_cost_inr_per_year"] + d_e) - 1) < 1e-3


def test_sensitivity_moves_the_right_way():
    for s in sensitivity(WEEKLY, ASSUMPTIONS):
        if s["assumption"] in ("Community-scale battery premium", "Battery tariff", "Smart plug cost per home"):
            assert s["breakeven_low"] < s["base"] < s["breakeven_high"]
        if s["assumption"] == "Stress weeks per year":      # more stress weeks -> more outage avoided
            assert s["breakeven_low"] < s["breakeven_high"]
