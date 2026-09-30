"""Phase 2 invariants: unit commitment, the 20-feeder fleet and the city map."""
import json
import types

import numpy as np
import pytest

from gridsetu import citymap
from gridsetu.config import load_scenario
from gridsetu.fleet import ADOPTION_LEVELS, run_fleet
from gridsetu.simulate import run_week
from gridsetu.uc import COMMITTABLE, lp_cost, run_uc


@pytest.fixture(scope="session")
def week():
    return run_week(load_scenario(), "stress week", cloudy_days=[2, 4], verbose=False)


@pytest.fixture(scope="session")
def uc(week):
    return run_uc(week.sc, week.city["baseline"]["inputs"])


@pytest.fixture(scope="session")
def fleet(week):
    return run_fleet(week)


# ---------------------------------------------------------------- unit commitment
def test_uc_status_is_binary_and_gates_output(week, uc):
    st = uc.status.values
    assert set(np.unique(st)) <= {0.0, 1.0}
    for g in uc.status.columns:
        off = uc.status[g].values < 0.5
        assert np.all(uc.gen[g].values[off] < 1e-3), f"{g} produces while off"


def test_uc_respects_minimum_up_time(week, uc):
    spd = week.sc.steps_per_day
    for g in uc.status.columns:
        up = int(week.sc.raw["unit_commitment"].get(g, {}).get("min_up_h", 1) / week.sc.dt_h)
        s = uc.status[g].values
        for d in range(week.sc.n_days):
            day = s[d * spd:(d + 1) * spd]
            starts = np.flatnonzero((day[1:] > 0.5) & (day[:-1] < 0.5)) + 1
            for t in starts:
                if t + up <= spd:        # the rule is enforced within each daily problem
                    assert day[t:t + up].min() > 0.5, f"{g} stopped before its minimum up time"


def test_uc_counts_and_costs_are_consistent(week, uc):
    assert set(uc.startups) == {g for g, v in week.sc.generators.items() if v["kind"] in COMMITTABLE}
    assert uc.cost_inr["total"] == pytest.approx(uc.cost_inr["energy"] + uc.cost_inr["startup"] + uc.cost_inr["shed"])
    assert np.isfinite(uc.price.values).all()
    lp = lp_cost(week.sc, week.city["baseline"]["inputs"], week.city["baseline"]["da"])
    # same demand, similar plant fleet: the two schedules should be within a few percent
    assert abs(uc.cost_inr["total"] - lp["total"]) / lp["total"] < 0.05


# ---------------------------------------------------------------- fleet
def test_fleet_has_every_rotation_group(week, fleet):
    groups = sorted(r["group"] for r in fleet["feeders"])
    assert groups == list(range(int(week.sc.regions["R3"]["domestic_feeder_groups"])))
    assert sorted(r["rank"] for r in fleet["feeders"]) == groups


def test_fleet_pilot_row_matches_pilot_feeder(week, fleet):
    pilot = next(r for r in fleet["feeders"] if r["is_pilot"])
    for mode in ("baseline", "gridsetu"):
        m = week.feeder[mode].metrics
        assert pilot[mode]["critical_outage_hours"] == pytest.approx(m["critical_outage_hours"])
        assert pilot[mode]["total_unserved_kwh"] == pytest.approx(m["total_unserved_kwh"])


def test_gridsetu_never_worse_for_critical_loads(fleet):
    for r in fleet["feeders"]:
        assert r["gridsetu"]["critical_outage_hours"] <= r["baseline"]["critical_outage_hours"] + 1e-9, r["id"]
        assert r["gridsetu"]["overload_trips"] <= r["baseline"]["overload_trips"], r["id"]


def test_adoption_curve_is_monotone_and_complete(fleet):
    curve = fleet["curve"]
    assert [c["adoption"] for c in curve] == list(ADOPTION_LEVELS)
    for key in ("critical_site_hours", "critical_outage_hours", "overload_trips"):
        vals = [c[key] for c in curve]
        assert all(b <= a + 1e-9 for a, b in zip(vals, vals[1:])), key
    assert curve[-1]["critical_site_hours"] == 0
    assert curve[0]["batteries_kwh"] == 0 and curve[-1]["feeders"] == len(fleet["feeders"])


# ---------------------------------------------------------------- map
def test_procedural_map_is_inside_bounds(fleet, monkeypatch, tmp_path):
    monkeypatch.setattr(citymap, "OSM_FILE", tmp_path / "missing.geojson")
    m = citymap.build_map(fleet["feeders"])
    assert m["source"] == "procedural" and len(m["feeders"]) == len(fleet["feeders"])
    for f in m["feeders"]:
        assert 0 <= f["x"] <= m["width"] and 0 <= f["y"] <= m["height"]
        assert citymap.region_of(f["x"], f["y"]) == "R3"
    for r in m["roads"]:
        for x, y in r["pts"]:
            assert 0 <= x <= m["width"] and 0 <= y <= m["height"]


def test_fetch_osm_writes_geojson_and_map_uses_it(fleet, monkeypatch, tmp_path):
    ways = [{"type": "way", "tags": {"highway": "primary", "name": "Avinashi Road"},
             "geometry": [{"lat": 11.00, "lon": 77.00}, {"lat": 11.03, "lon": 77.08}]},
            {"type": "way", "tags": {"railway": "rail"},
             "geometry": [{"lat": 10.99, "lon": 76.99}, {"lat": 11.06, "lon": 77.19}]}]

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"elements": ways + [{"type": "node"}]}

    monkeypatch.setitem(__import__("sys").modules, "httpx", types.SimpleNamespace(post=lambda *a, **k: Resp()))
    out = tmp_path / "roads.geojson"
    res = citymap.fetch_osm(out=out)
    assert res["features"] == 2
    gj = json.loads(out.read_text())
    assert gj["features"][0]["properties"]["name"] == "Avinashi Road"
    monkeypatch.setattr(citymap, "OSM_FILE", out)
    m = citymap.build_map(fleet["feeders"])
    assert m["source"] == "osm" and "OpenStreetMap" in m["attribution"]
    assert any(r["cls"] == "rail" for r in m["roads"])
