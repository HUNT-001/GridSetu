"""City map geometry for the fleet view (Phase 2).

Two sources, same output shape (a local frame in kilometres, x east, y north):

  osm         real streets from OpenStreetMap, fetched once with `gridsetu fetch-osm`
              (Overpass API) into data/osm/roads.geojson. Regions, substations, plants
              and feeder villages are then placed on that street network.
  procedural  a generated street network with the same structure, used when no OSM
              extract is present (for example on a machine without internet).

The map is geometry only; what is lit, shed or islanded comes from the run payloads."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OSM_FILE = ROOT / "data" / "osm" / "roads.geojson"
W, H = 24.0, 14.0
# default extract: Coimbatore's south-eastern periphery (Singanallur to Irugur and Sulur)
DEFAULT_BBOX = (10.975, 76.985, 11.075, 77.205)   # south, west, north, east

REGION_SEEDS = {"R1": (4.2, 9.2), "R2": (11.8, 8.8), "R3": (18.2, 5.0)}
SUBSTATIONS = {"NAT": (0.6, 10.6), "R1": (4.6, 9.6), "R2": (12.0, 8.4), "R3": (17.2, 5.2)}
PLANTS = {"G1A": ("coal", (2.2, 12.2)), "G1B": ("coal", (2.9, 12.4)), "G2": ("gas", (13.8, 11.4)),
          "H1": ("hydro", (22.4, 12.0)), "S1": ("solar", (20.8, 1.6)), "W1": ("wind", (23.0, 7.2))}


def region_of(x: float, y: float) -> str:
    d = {r: math.hypot(x - sx, y - sy) * (0.85 if r == "R3" else 1.0) for r, (sx, sy) in REGION_SEEDS.items()}
    return min(d, key=d.get)


def _jitter_line(rng, pts, amp, n=12):
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append([x0 + (x1 - x0) * t + rng.normal(0, amp), y0 + (y1 - y0) * t + rng.normal(0, amp)])
    out.append(list(pts[-1]))
    return out


def _clip(pts):
    return [[round(min(max(x, 0), W), 3), round(min(max(y, 0), H), 3)] for x, y in pts]


def procedural_roads(rng) -> list[dict]:
    roads = []
    cx, cy = REGION_SEEDS["R2"]
    for k, ang in enumerate(np.linspace(0, 2 * np.pi, 7, endpoint=False) + 0.3):
        far = (cx + 16 * math.cos(ang), cy + 16 * math.sin(ang))
        roads.append({"cls": "primary", "pts": _clip(_jitter_line(rng, [(cx, cy), far], 0.05, 30))})
    ring = [(cx + 5.2 * math.cos(a) * (1 + 0.06 * math.sin(3 * a)), cy + 4.2 * math.sin(a)) for a in np.linspace(0, 2 * np.pi, 80)]
    roads.append({"cls": "trunk", "pts": _clip(ring)})
    # urban grid (R2), rotated
    rot = math.radians(12)
    for i in np.arange(-3.6, 3.61, 0.36):
        for horiz in (True, False):
            seg = []
            for j in np.arange(-3.6, 3.61, 0.36):
                u, v = (j, i) if horiz else (i, j)
                if u * u + v * v > 3.6 ** 2 or rng.random() < 0.06:
                    if len(seg) > 1:
                        roads.append({"cls": "residential", "pts": _clip(seg)})
                    seg = []
                    continue
                seg.append((cx + u * math.cos(rot) - v * math.sin(rot), cy + u * math.sin(rot) + v * math.cos(rot)))
            if len(seg) > 1:
                roads.append({"cls": "residential", "pts": _clip(seg)})
    # industrial estate (R1)
    ix, iy = REGION_SEEDS["R1"]
    for i in np.arange(-2.4, 2.41, 0.6):
        roads.append({"cls": "tertiary", "pts": _clip([(ix - 2.4, iy + i), (ix + 2.4, iy + i)])})
        roads.append({"cls": "tertiary", "pts": _clip([(ix + i, iy - 2.4), (ix + i, iy + 2.4)])})
    # railway
    rail = _clip(_jitter_line(rng, [(0, 11.2), (8, 9.8), (15, 7.6), (24, 3.4)], 0.02, 20))
    return roads + [{"cls": "rail", "pts": rail}]


def _poisson_centres(rng, n, region="R3", min_d=1.25):
    pts = []
    tries = 0
    while len(pts) < n and tries < 20000:
        tries += 1
        x, y = rng.uniform(13.5, 23.5), rng.uniform(0.6, 11.0)
        if region_of(x, y) != region or math.hypot(x - SUBSTATIONS["R3"][0], y - SUBSTATIONS["R3"][1]) < 0.9:
            continue
        if all(math.hypot(x - a, y - b) >= min_d for a, b in pts):
            pts.append((x, y))
        if tries % 4000 == 0:
            min_d *= 0.9
    return pts


def load_osm(path: Path) -> tuple[list[dict], dict] | None:
    if not path.exists():
        return None
    gj = json.loads(path.read_text())
    lines = []
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            lines.append((f.get("properties", {}).get("highway") or f.get("properties", {}).get("railway") or "road",
                          g["coordinates"]))
    if not lines:
        return None
    lon = np.array([c[0] for _, cs in lines for c in cs])
    lat = np.array([c[1] for _, cs in lines for c in cs])
    lon0, lat0 = lon.min(), lat.min()
    kx = 111.32 * math.cos(math.radians(lat.mean()))
    ky = 110.57
    w, h = (lon.max() - lon0) * kx, (lat.max() - lat0) * ky
    s = min(W / w, H / h)
    cls_map = {"motorway": "trunk", "trunk": "trunk", "primary": "primary", "secondary": "primary",
               "tertiary": "tertiary", "rail": "rail"}
    roads = []
    for cls, cs in lines:
        pts = [[round((c[0] - lon0) * kx * s, 3), round((c[1] - lat0) * ky * s, 3)] for c in cs]
        roads.append({"cls": cls_map.get(cls, "residential"), "pts": pts})
    meta = {"source": "osm", "bbox": [float(lat0), float(lon0), float(lat.max()), float(lon.max())],
            "km_per_unit": 1 / s, "attribution": "© OpenStreetMap contributors (ODbL)"}
    return roads, meta


def build_map(fleet_rows: list[dict] | None = None, seed: int = 20260914) -> dict:
    rng = np.random.default_rng(seed)
    osm = load_osm(OSM_FILE)
    if osm:
        roads, meta = osm
    else:
        roads = procedural_roads(rng)
        meta = {"source": "procedural", "km_per_unit": 1.0,
                "attribution": "Generated street network (run `gridsetu fetch-osm` for real OpenStreetMap streets)"}
    n = len(fleet_rows) if fleet_rows else 20
    centres = _poisson_centres(np.random.default_rng(seed + 1), n)
    feeders = []
    for i, (x, y) in enumerate(centres):
        row = fleet_rows[i] if fleet_rows else {"group": i, "households": 400}
        hh = int(row["households"])
        r = 0.18 + 0.00045 * hh
        k = max(20, hh // 5)                 # one dot per five homes
        ang = rng.uniform(0, 2 * np.pi, k)
        rad = r * np.sqrt(rng.uniform(0, 1, k))
        dots = [[round(x + a * math.cos(t), 3), round(y + a * math.sin(t) * 0.8, 3)] for a, t in zip(rad, ang)]
        # local lanes
        lanes = [{"cls": "residential", "pts": _clip([(x - r, y + dy), (x + r, y + dy)])} for dy in (-r / 2, 0, r / 2)]
        lanes.append({"cls": "residential", "pts": _clip([(x, y - r), (x, y + r)])})
        roads.extend(lanes)
        feeders.append({"group": int(row["group"]), "x": round(x, 3), "y": round(y, 3), "radius": round(r, 3),
                        "dots": dots, "line": _clip(_jitter_line(rng, [SUBSTATIONS["R3"], (x, y)], 0.02, 4))})
    # load dots for R1 and R2 (for shedding by class), deterministic
    zones = []
    for reg, cls_mix, spread, count in (("R2", {"domestic": 0.55, "commercial": 0.45}, 3.2, 900),
                                         ("R1", {"industrial": 0.6, "domestic": 0.4}, 2.3, 420)):
        sx, sy = REGION_SEEDS[reg]
        pts = rng.normal(0, spread / 2.2, size=(count, 2))
        classes = rng.choice(list(cls_mix), size=count, p=list(cls_mix.values()))
        zones.append({"region": reg, "dots": [[round(sx + a, 3), round(sy + b * 0.8, 3), c, round(float(rng.random()), 3)]
                                              for (a, b), c in zip(pts, classes)]})
    lines220 = [["NAT", "R1"], ["R1", "R2"], ["R2", "R3"], ["R1", "R3"]]
    return {"width": W, "height": H, **meta, "roads": roads, "regions": {r: {"label_at": p} for r, p in REGION_SEEDS.items()},
            "substations": SUBSTATIONS, "plants": {k: {"kind": v[0], "at": v[1]} for k, v in PLANTS.items()},
            "lines_220kv": lines220, "feeders": feeders, "zones": zones}


def fetch_osm(bbox=DEFAULT_BBOX, out: Path = OSM_FILE, endpoint: str = "https://overpass-api.de/api/interpreter") -> dict:
    """Download roads and railways in `bbox` from the Overpass API into a GeoJSON file."""
    import httpx
    s, w, n, e = bbox
    q = f"""[out:json][timeout:90];
(way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified)$"]({s},{w},{n},{e});
 way["railway"="rail"]({s},{w},{n},{e}););
out geom;"""
    r = httpx.post(endpoint, data={"data": q}, timeout=120, headers={"User-Agent": "gridsetu/1.0"})
    r.raise_for_status()
    feats = []
    for el in r.json().get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in el["geometry"]]
        feats.append({"type": "Feature", "properties": {k: tags[k] for k in ("highway", "railway", "name") if k in tags},
                      "geometry": {"type": "LineString", "coordinates": coords}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                               "attribution": "© OpenStreetMap contributors, ODbL"}))
    return {"features": len(feats), "path": str(out)}
