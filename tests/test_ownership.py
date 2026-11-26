import json
from pathlib import Path

from gridsetu.ownership import run_study

ROOT = Path(__file__).resolve().parents[1]


def test_ownership_adds_up(tmp_path):
    (tmp_path / "economics.json").write_text(
        (ROOT / "outputs" / "economics" / "economics.json").read_text(encoding="utf-8"), encoding="utf-8")
    o = run_study(tmp_path)
    c = o["annual_cost_inr"]
    assert c["total"] == c["battery_service"] + c["smart_plugs"] + c["controller_comms"] + c["local_operator"]
    assert o["who_pays"]["discom_availability_fee"] == c["battery_service"] + c["controller_comms"] + c["local_operator"]
    assert o["who_pays"]["homes_extra"] == 0
    back = o["discom_gets_back"]
    assert abs(o["discom_net_cost"] - (o["who_pays"]["discom_availability_fee"]
                                       - back["transformer_upgrade_deferred"] - back["technical_losses_avoided_inr"])) <= 2
    assert 0 < o["discom_net_cost_per_avoided_outage_kwh"] < 100
    # the committed result is what this code produces
    committed = json.loads((ROOT / "outputs" / "economics" / "ownership.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(o))
