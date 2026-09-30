/* City map renderer (Canvas 2D) for the fleet view.
 *
 * Static layers (ground, streets, railway) are drawn once into an offscreen canvas and
 * blitted each frame. Dynamic layers follow the shared playhead: power along the 220 kV
 * lines and feeders, lit or dark homes, and each feeder's controller state. Feeders ease
 * between states (~120 ms) so a step change or a change of adoption level reads as a
 * fade rather than a flicker. */
import type { CityPayload, FleetPayload, MapPayload, Pt } from "@/lib/types";
import { at, clamp, decodeB64 } from "@/lib/utils";
import { readPalette, type Palette } from "@/components/city/scene";

const rgba = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

export type FeederMode = "baseline" | "gridsetu";
export interface FeederHit { group: number; x: number; y: number }

interface FeederAnim {
  lit: number;        // 0..1 share of homes shown lit
  setu: number;       // 0..1 GridSetu acting (teal halo)
  island: number;     // 0..1 critical loads islanded on the battery
  phase: number;      // particle phase along the feeder line
}

export class MapScene {
  private ctx: CanvasRenderingContext2D;
  private base: HTMLCanvasElement | null = null;
  private map: MapPayload | null = null;
  private fleet: FleetPayload | null = null;
  private city: CityPayload | null = null;
  private states: Record<FeederMode, Uint8Array> | null = null;
  private imports: Record<FeederMode, Int16Array> | null = null;
  private rowOf = new Map<number, number>();         // group -> row index in fleet payload
  private adopted = new Set<number>();
  private anim = new Map<number, FeederAnim>();
  private linePhase: Record<string, number> = {};
  private cssW = 800;
  private scale = 1;
  private dpr = 1;
  regionName: Record<string, string> = {};
  selected: number | null = null;
  hover: number | null = null;
  pal: Palette;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    this.pal = readPalette();
  }

  onTheme() { this.pal = readPalette(); this.base = null; }

  setData(map: MapPayload | null, fleet: FleetPayload | null, city: CityPayload | null) {
    const mapChanged = map !== this.map;
    this.map = map; this.fleet = fleet; this.city = city;
    if (mapChanged) this.base = null;
    this.states = null; this.imports = null; this.rowOf.clear();
    if (fleet) {
      fleet.feeders.forEach((f, i) => this.rowOf.set(f.group, i));
      this.states = { baseline: decodeB64(fleet.states_b64.baseline), gridsetu: decodeB64(fleet.states_b64.gridsetu) };
      const i16 = (b64: string) => { const u = decodeB64(b64); return new Int16Array(u.buffer, u.byteOffset, u.byteLength / 2); };
      this.imports = { baseline: i16(fleet.import_b64.baseline), gridsetu: i16(fleet.import_b64.gridsetu) };
    }
  }

  setAdopted(groups: Set<number>) { this.adopted = groups; }

  resize(cssW: number) {
    if (!this.map) return;
    this.cssW = cssW;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.scale = cssW / this.map.width;
    const cssH = cssW * (this.map.height / this.map.width);
    this.canvas.width = Math.round(cssW * this.dpr);
    this.canvas.height = Math.round(cssH * this.dpr);
    this.canvas.style.height = `${cssH}px`;
    this.base = null;
  }

  /** map units (km, y north) -> CSS pixels */
  px(p: Pt | [number, number]): [number, number] {
    return [p[0] * this.scale, (this.map!.height - p[1]) * this.scale];
  }

  hitTest(cssX: number, cssY: number): FeederHit | null {
    if (!this.map) return null;
    let best: FeederHit | null = null, bd = Infinity;
    for (const f of this.map.feeders) {
      const [x, y] = this.px([f.x, f.y]);
      const d = Math.hypot(cssX - x, cssY - y);
      const r = Math.max(14, f.radius * this.scale * 1.3);
      if (d < r && d < bd) { bd = d; best = { group: f.group, x, y }; }
    }
    return best;
  }

  private drawBase() {
    const m = this.map!, p = this.pal;
    const c = document.createElement("canvas");
    c.width = this.canvas.width; c.height = this.canvas.height;
    const g = c.getContext("2d")!;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.fillStyle = p.dark ? "#0a1a30" : "#eef2f6";
    g.fillRect(0, 0, this.cssW, m.height * this.scale);
    // region tints
    const tint: Record<string, string> = { R1: p.r1, R2: p.r2, R3: p.r3 };
    for (const [r, v] of Object.entries(m.regions)) {
      const [x, y] = this.px(v.label_at);
      const grad = g.createRadialGradient(x, y, 0, x, y, 7 * this.scale);
      grad.addColorStop(0, rgba(tint[r] ?? p.teal, p.dark ? 0.10 : 0.08));
      grad.addColorStop(1, rgba(tint[r] ?? p.teal, 0));
      g.fillStyle = grad;
      g.fillRect(0, 0, this.cssW, m.height * this.scale);
    }
    const widths: Record<string, number> = { trunk: 2.2, primary: 1.6, tertiary: 1.1, residential: 0.6, rail: 1.2 };
    const alpha: Record<string, number> = { trunk: 0.34, primary: 0.26, tertiary: 0.2, residential: 0.14, rail: 0.4 };
    for (const cls of ["residential", "tertiary", "primary", "trunk", "rail"]) {
      g.strokeStyle = rgba(p.fg, alpha[cls] ?? 0.12);
      g.lineWidth = (widths[cls] ?? 0.6) * Math.max(0.7, this.scale / 50);
      g.setLineDash(cls === "rail" ? [5, 4] : []);
      g.lineCap = "round"; g.lineJoin = "round";
      g.beginPath();
      for (const r of m.roads) {
        if (r.cls !== cls || r.pts.length < 2) continue;
        const [x0, y0] = this.px(r.pts[0]);
        g.moveTo(x0, y0);
        for (let i = 1; i < r.pts.length; i++) { const [x, y] = this.px(r.pts[i]); g.lineTo(x, y); }
      }
      g.stroke();
    }
    g.setLineDash([]);
    this.base = c;
  }

  private flowOf(key: string, step: number): { mw: number; limit: number } {
    const c = this.city;
    if (!c) return { mw: 0, limit: 1 };
    const s = c.scenarios.baseline;
    if (key === "NAT-R1") return { mw: at(s.gen.IMP, step), limit: 90 };
    if (s.flow[key]) return { mw: at(s.flow[key], step), limit: c.tie_limit[key] ?? 100 };
    const rev = key.split("-").reverse().join("-");
    if (s.flow[rev]) return { mw: -at(s.flow[rev], step), limit: c.tie_limit[rev] ?? 100 };
    return { mw: 0, limit: 1 };
  }

  /** Text with a halo in the ground colour, so labels stay legible over dots and lines. */
  private label(text: string, x: number, y: number, fill: string, font: string, align: CanvasTextAlign = "left") {
    const ctx = this.ctx;
    ctx.font = font; ctx.textAlign = align;
    ctx.lineJoin = "round"; ctx.lineWidth = 3.5;
    ctx.strokeStyle = this.pal.dark ? "rgba(10,26,48,0.9)" : "rgba(238,242,246,0.92)";
    ctx.strokeText(text, x, y);
    ctx.fillStyle = fill; ctx.fillText(text, x, y);
    ctx.textAlign = "left";
  }

  render(step: number, dt: number) {
    const ctx = this.ctx, p = this.pal, m = this.map;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    if (!m) { ctx.fillStyle = p.bg; ctx.fillRect(0, 0, this.cssW, this.cssW * 0.58); return; }
    if (!this.base) this.drawBase();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(this.base!, 0, 0);
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    const cz = at(this.city?.weather.cos_zenith, step);
    const night = 1 - clamp(cz * 3.2, 0, 1);
    if (night > 0.02) {
      ctx.fillStyle = p.dark ? `rgba(2,8,18,${0.35 * night})` : `rgba(40,60,90,${0.12 * night})`;
      ctx.fillRect(0, 0, this.cssW, m.height * this.scale);
    }
    const litCol = night > 0.3 ? "#ffc861" : p.dark ? "#d6b77a" : "#d9962e";
    const k = 1 - Math.exp(-dt / 0.12);

    // ---- R1 / R2 load zones: dots dim with that class's shedding
    const s = this.city?.scenarios.baseline;
    for (const z of m.zones) {
      const frac: Record<string, number> = {};
      if (s) for (const c of Object.keys(s.load[z.region] ?? {})) {
        const l = at(s.load[z.region][c], step), sh = at(s.shed[z.region][c], step);
        frac[c] = l > 0 ? sh / l : 0;
      }
      for (const [x, y, cls, r] of z.dots) {
        const [cx, cy] = this.px([x, y]);
        const on = r >= (frac[cls] ?? 0);
        ctx.fillStyle = on ? rgba(litCol, 0.35 + 0.5 * night) : rgba(p.fg, 0.1);
        ctx.fillRect(cx - 1, cy - 1, 2, 2);
      }
    }

    // ---- 220 kV lines with moving power
    for (const [a, b] of m.lines_220kv) {
      const A = this.px(m.substations[a]), B = this.px(m.substations[b]);
      const { mw, limit } = this.flowOf(`${a}-${b}`, step);
      const load = Math.abs(mw) / (limit || 1);
      const col = load > 0.98 ? p.danger : load > 0.75 ? p.amber : p.teal;
      ctx.strokeStyle = rgba(p.fg, 0.35); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
      const key = `${a}-${b}`;
      const len = Math.hypot(B[0] - A[0], B[1] - A[1]);
      this.linePhase[key] = ((this.linePhase[key] ?? 0) + dt * (0.06 + load * 0.35) * Math.sign(mw || 1) * (260 / Math.max(len, 1)) + 1) % 1;
      const n = Math.max(3, Math.round(len / 28));
      if (Math.abs(mw) > 0.5) {
        ctx.fillStyle = col;
        for (let i = 0; i < n; i++) {
          const t = (i / n + this.linePhase[key]) % 1;
          ctx.beginPath(); ctx.arc(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, 1.8 + load * 1.6, 0, Math.PI * 2); ctx.fill();
        }
      }
    }

    // ---- R3 feeders
    const codes = this.fleet?.state_codes ?? [];
    const nSteps = this.fleet?.n ?? 1;
    const i = clamp(Math.floor(step), 0, nSteps - 1);
    for (const f of m.feeders) {
      const row = this.rowOf.get(f.group);
      const info = row != null ? this.fleet!.feeders[row] : null;
      const mode: FeederMode = this.adopted.has(f.group) ? "gridsetu" : "baseline";
      let st = "normal", imp = 0;
      if (row != null && this.states && this.imports) {
        st = codes[this.states[mode][row * nSteps + i]] ?? "normal";
        imp = Math.max(0, this.imports[mode][row * nSteps + i]);
      }
      const tripped = st.includes("trip") && st !== "overload_event";
      const islanded = tripped && st.includes("island");
      const acting = mode === "gridsetu" && (st === "cap" || st === "sps_relief");
      const a = this.anim.get(f.group) ?? { lit: 1, setu: 0, island: 0, phase: Math.random() };
      a.lit += ((tripped ? 0 : acting ? 0.75 : 1) - a.lit) * k;
      a.setu += ((mode === "gridsetu" ? 1 : 0) - a.setu) * k;
      a.island += ((islanded ? 1 : 0) - a.island) * k;
      this.anim.set(f.group, a);

      // feeder line from the R3 substation, coloured by transformer loading
      const rating = info?.rating_kw ?? 300;
      const load = imp / rating;
      const col = tripped ? rgba(p.fg, 0.18) : load > 1 ? p.danger : load > 0.85 ? p.amber : p.teal;
      ctx.strokeStyle = tripped ? rgba(p.fg, 0.2) : rgba(p.fg, 0.28); ctx.lineWidth = 1.2;
      ctx.beginPath();
      f.line.forEach((pt, j) => { const [x, y] = this.px(pt); if (j) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      ctx.stroke();
      if (!tripped && imp > 1) {
        a.phase = (a.phase + dt * (0.15 + load * 0.5)) % 1;
        ctx.fillStyle = col;
        const L = f.line;
        for (let q = 0; q < 3; q++) {
          const t = (q / 3 + a.phase) % 1;
          const seg = t * (L.length - 1), j = Math.floor(seg), u = seg - j;
          const P = this.px([L[j][0] + (L[j + 1][0] - L[j][0]) * u, L[j][1] + (L[j + 1][1] - L[j][1]) * u]);
          ctx.beginPath(); ctx.arc(P[0], P[1], 1.6 + Math.min(load, 1.2) * 1.2, 0, Math.PI * 2); ctx.fill();
        }
      }

      // homes
      const [cx, cy] = this.px([f.x, f.y]);
      const R = f.radius * this.scale;
      if (a.setu > 0.02) {
        ctx.strokeStyle = rgba(p.teal, 0.25 + 0.55 * a.setu); ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(cx, cy, R + 5, 0, Math.PI * 2); ctx.stroke();
      }
      const nd = f.dots.length;
      for (let d = 0; d < nd; d++) {
        const [dx, dy] = this.px(f.dots[d]);
        const on = (d / nd) < a.lit;
        ctx.fillStyle = on ? rgba(litCol, 0.5 + 0.45 * night) : rgba(p.fg, p.dark ? 0.12 : 0.18);
        ctx.fillRect(dx - 1.2, dy - 1.2, 2.4, 2.4);
      }
      // critical-load marker: lit while supplied (grid or island)
      if (info && info.baseline.critical_sites > 0) {
        const critOn = !tripped || a.island > 0.5;
        ctx.fillStyle = critOn ? (a.island > 0.5 ? p.teal : rgba(p.fg, 0.85)) : p.danger;
        ctx.fillRect(cx - 1, cy - 4, 2, 8); ctx.fillRect(cx - 4, cy - 1, 8, 2);
      }
      if (this.selected === f.group || this.hover === f.group) {
        ctx.strokeStyle = p.fg; ctx.lineWidth = this.selected === f.group ? 1.6 : 1;
        ctx.setLineDash(this.selected === f.group ? [] : [3, 3]);
        ctx.beginPath(); ctx.arc(cx, cy, R + 9, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
      }
      if (this.scale > 34) {
        this.label(info?.id ?? `F${f.group}`, cx + R + 6, cy - R, tripped ? p.danger : p.muted,
          `500 11px "Source Code Pro Variable", monospace`);
      }
    }

    // ---- substations and plants
    for (const [k2, pt] of Object.entries(m.substations)) {
      const [x, y] = this.px(pt);
      ctx.fillStyle = p.dark ? "#0c1f3a" : "#ffffff"; ctx.strokeStyle = p.fg; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.rect(x - 6, y - 6, 12, 12); ctx.fill(); ctx.stroke();
      const name = k2 === "NAT" ? "National grid" : `${k2} ${this.regionName[k2] ?? ""}`.trim();
      this.label(name, x + 9, y - 8, p.fg, `600 11.5px "Inter Variable", Inter, sans-serif`);
    }
    const kindCol: Record<string, string> = { coal: p.fg, gas: p.r2, hydro: p.r1, solar: p.amber, wind: p.r3 };
    const coal = Object.entries(m.plants).filter(([, v]) => v.kind === "coal").map(([g]) => g);
    for (const [gid, pl] of Object.entries(m.plants)) {
      const [x, y] = this.px(pl.at);
      const mw = at(s?.gen[gid], step);
      const off = mw < 0.5;
      ctx.fillStyle = off ? rgba(p.fg, 0.25) : kindCol[pl.kind] ?? p.fg;
      ctx.beginPath(); ctx.moveTo(x, y - 7); ctx.lineTo(x + 7, y + 5); ctx.lineTo(x - 7, y + 5); ctx.closePath(); ctx.fill();
      let text: string | null = `${gid} ${off ? "off" : `${mw.toFixed(0)} MW`}`;
      if (pl.kind === "coal") {                        // one label for the coal station
        if (gid !== coal[coal.length - 1]) continue;
        const tot = coal.reduce((a, g) => a + at(s?.gen[g], step), 0);
        const outs = coal.filter((g) => at(s?.gen[g], step) < 0.5);
        text = `Coal ${tot.toFixed(0)} MW${outs.length ? `, ${outs.join(" ")} off` : ""}`;
      }
      const right = x > this.cssW * 0.8;
      this.label(text, right ? x - 10 : x + 10, y + 4, off && pl.kind !== "coal" ? p.faint : p.muted,
        `500 11px "Source Code Pro Variable", monospace`, right ? "right" : "left");
    }
    // scale bar
    const kmPx = this.scale / (m.km_per_unit || 1);
    const bar = kmPx * (m.km_per_unit > 2 ? 5 : 2);
    const by = m.height * this.scale - 14;
    ctx.strokeStyle = p.muted; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(12, by); ctx.lineTo(12 + bar, by); ctx.moveTo(12, by - 4); ctx.lineTo(12, by); ctx.moveTo(12 + bar, by - 4); ctx.lineTo(12 + bar, by); ctx.stroke();
    ctx.fillStyle = p.muted; ctx.font = `500 11px "Inter Variable", Inter, sans-serif`;
    ctx.fillText(`${m.km_per_unit > 2 ? 5 : 2} km`, 16 + bar, by + 3);
  }
}
