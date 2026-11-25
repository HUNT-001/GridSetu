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


def test_cost_inputs_come_from_config_unchanged():
    # moving the assumptions from economics.py into config/city.yaml must not move any figure
    from gridsetu.economics import load_inputs
    a = load_inputs()["assumptions"]
    assert a["bess_benchmark_inr_per_mw_month"] == 2.3e5 and a["community_scale_premium"] == 2.0
    assert a["smart_plug_inr_per_home"] == 1500.0 and a["controller_comms_inr_per_year"] == 25000.0
    assert a["stress_weeks_per_year"] == 13 and a["homes"] == 1090


def test_capex_method_waits_for_sourced_prices():
    from gridsetu.economics import capex_method, load_inputs
    r = capex_method(WEEKLY, load_inputs())
    assert r["status"] == "PENDING_SOURCE"
    assert "battery_inr_per_kwh" in r["missing_inputs"]
    assert set(r) == {"status", "missing_inputs", "note"}      # no figures while inputs are missing


def test_capex_method_arithmetic_with_test_inputs():
    # placeholder prices for the arithmetic only; never real or default values
    from gridsetu.economics import capex_method, load_inputs
    inputs = load_inputs()
    inputs["capex"] = {"battery_inr_per_kwh": 10000.0, "battery_second_life_inr_per_kwh": 5000.0,
                       "inverter_inr_per_kw": 1000.0, "controller_meters_comms_inr": 100000.0,
                       "installation_inr": 0.0, "om_pct_of_capex_per_year": 10.0,
                       "life_years": 10, "discount_rate_pct": 0.0}
    w = {wk: {v: {**d, "dark_home_hours": 100.0 if v == "baseline" else 0.0} for v, d in x.items()}
         for wk, x in WEEKLY.items()}
    r = capex_method(w, inputs)
    build = 10000 * 200 + 1000 * 100 + 100000
    assert r["build_cost_inr"] == build
    life = build * (1 + 0.1 * 10)
    assert r["life_cost_inr"] == round(life)
    assert abs(r["cost_per_kwh_one_cycle_per_day_inr"] - life / (inputs["usable_kwh"] * 365 * 10)) < 0.01
    assert abs(r["cost_per_kwh_at_model_cycling_inr"] - life / (52 * 900 * 10)) < 0.01
    assert abs(r["cost_per_avoided_home_outage_hour_inr"] - life / (52 * 100 * 10)) < 0.01


def test_tariff_method_per_outage_hour_and_per_battery_kwh():
    w = {wk: {v: {**d, "dark_home_hours": 100.0 if v == "baseline" else 20.0} for v, d in x.items()}
         for wk, x in WEEKLY.items()}
    a = annual(w, ASSUMPTIONS)
    assert a["home_outage_hours_avoided_per_year"] == 52 * 80
    assert abs(a["cost_per_avoided_home_outage_hour_inr"]
               - (a["total_cost_inr_per_year"] + a["extra_energy_cost_inr_per_year"]) / (52 * 80)) < 0.01
    assert a["battery_discharge_kwh_per_year"] == 52 * 900
    assert abs(a["battery_cost_per_kwh_delivered_inr"] - a["costs_inr_per_year"]["battery"] / (52 * 900)) < 0.01


def test_reserve_price_adder_build_up():
    from gridsetu.feeder import reserve_price_adder
    f = {"reserve_price": {"adder_inr_kwh": 2.0, "build_up_inr_kwh": {"a": None, "b": 0.5}}}
    assert reserve_price_adder(f) == 2.0                 # incomplete build-up: flat adder stays
    f["reserve_price"]["build_up_inr_kwh"]["a"] = 1.0
    assert reserve_price_adder(f) == 1.5                 # complete build-up replaces it
    assert reserve_price_adder({}) == 2.0
