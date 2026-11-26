"""Who owns GridSetu, who runs it, who pays: the funding model for one feeder.

    python -m gridsetu ownership          # writes outputs/economics/ownership.json

Reads the business case (outputs/economics/economics.json) and the low-voltage study
(outputs/lv/summary.json), and sets out what the recommended model costs each party per year:
the DISCOM buys feeder reliability as a service from a local operator (an availability fee, the
same contract form as India's utility battery tenders); smart plugs are a one-off grant; homes
pay nothing extra. Every input is tagged SOURCED (with its source) or ASSUMED.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAKH = 1e5
WEEKS_STRESS, WEEKS_REP = 13, 39          # the business case's year: 13 stress + 39 representative weeks

INPUTS = {
    "local_operator_inr_per_month": {
        "value": 8000, "tag": "ASSUMED",
        "note": "a part-time trained local operator (for example from a women's self-help group): "
                "daily checks, first-line faults, the residents' help desk"},
    "transformer_augmentation_inr": {
        "value": 19.989 * LAKH, "tag": "SOURCED",
        "note": "MSEDCL activity rates (Nov 2024), item 1305, augmentation of an existing "
                "distribution transformer centre from 315 to 630 kVA, DPR rate (Rs lakh)",
        "url": "https://mahadiscom.in/supplier/wp-content/uploads/2024/11/Activity_Rates.pdf"},
    "discom_cost_of_capital": {
        "value": 0.095, "tag": "ASSUMED",
        "note": "deferring that augmentation by a year is worth its capital cost x this rate"},
    "tn_free_power_subsidy_inr_per_year": {
        "value": 1730e7, "tag": "SOURCED",
        "note": "Tamil Nadu, May 2026: free domestic units raised from 100 to 200 per bill; adds "
                "about Rs 1,730 crore a year to the subsidy (DT Next, 10 May 2026; TNERC approved "
                "Rs 1,545 crore for 326 days of 2026-27, Mercom, 28 May 2026)",
        "url": "https://www.dtnext.in/news/tamilnadu/free-power-supply-up-to-200-units-to-benefit-146-cr-domestic-consumers"},
    "tn_free_power_extra_consumers": {
        "value": 1.46e7, "tag": "SOURCED", "note": "consumers who gain from the change (DT Next)"},
    "vgf_inr_per_mwh": {
        "value": 18 * LAKH, "tag": "SOURCED",
        "note": "Ministry of Power viability gap funding, second tranche (June 2025): Rs 1.8 "
                "million per MWh of battery storage, 30 GWh (Mercom, 10 June 2025). For grid-scale "
                "tenders; community batteries would need to be aggregated into a state tender",
        "url": "https://mercomindia.com/government-54-billion-vgf-battery-storage"},
}


def _v(key: str) -> float:
    return float(INPUTS[key]["value"])


def run_study(out_dir: str | Path = "outputs/economics") -> dict:
    out = Path(out_dir)
    econ = json.loads((out / "economics.json").read_text(encoding="utf-8"))   # the business case in out_dir
    lv = json.loads((ROOT / "outputs" / "lv" / "summary.json").read_text(encoding="utf-8"))
    a = econ["annual"]
    homes = int(econ["about"]["assumptions"]["homes"])
    c = a["costs_inr_per_year"]
    battery, plugs, controller = c["battery"], c["smart_plugs"], c["controller_comms"]
    operator = 12 * _v("local_operator_inr_per_month")

    # what the DISCOM gets back
    deferral = _v("transformer_augmentation_inr") * _v("discom_cost_of_capital")
    loss_kwh = (WEEKS_STRESS * (lv["stress/baseline"]["technical_loss_kwh"]
                                - lv["stress/gridsetu_distributed"]["technical_loss_kwh"])
                + WEEKS_REP * (lv["representative/baseline"]["technical_loss_kwh"]
                               - lv["representative/gridsetu_distributed"]["technical_loss_kwh"]))
    loss_value = loss_kwh * a["avg_purchase_price_inr_per_kwh"]["gridsetu"]

    availability_fee = battery + controller + operator          # paid by the DISCOM to the operator
    discom_net = availability_fee - deferral - loss_value
    avoided = a["unserved_avoided_kwh_per_year"]
    total = battery + plugs + controller + operator
    tn_per_home_month = _v("tn_free_power_subsidy_inr_per_year") / _v("tn_free_power_extra_consumers") / 12

    res = {
        "about": {"label": "SIMULATION-based costs; funding model for one feeder (1 battery, "
                           f"{homes} homes). Rs per year unless stated.",
                  "inputs": INPUTS},
        "homes": homes,
        "annual_cost_inr": {"battery_service": round(battery), "smart_plugs": round(plugs),
                            "controller_comms": round(controller), "local_operator": round(operator),
                            "total": round(total)},
        "per_home_per_month_inr": round(total / homes / 12, 1),
        "who_pays": {
            "discom_availability_fee": round(availability_fee),
            "plug_grant_one_off_inr": round(plugs * 5),
            "plug_grant_annualised": round(plugs),
            "homes_extra": 0,
        },
        "discom_gets_back": {
            "transformer_upgrade_deferred": round(deferral),
            "technical_losses_avoided_kwh": round(loss_kwh),
            "technical_losses_avoided_inr": round(loss_value),
        },
        "discom_net_cost": round(discom_net),
        "discom_net_cost_per_avoided_outage_kwh": round(discom_net / avoided, 2),
        "unserved_avoided_kwh_per_year": round(avoided),
        "vgf_if_aggregated_inr_one_off": round(_v("vgf_inr_per_mwh") * 0.2),
        "tn_free_power_increase_per_home_per_month_inr": round(tn_per_home_month, 1),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "ownership.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res
