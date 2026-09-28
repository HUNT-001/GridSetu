/* City scene renderer (Canvas 2D). One instance per <canvas>; drawn every animation
 * frame from the shared playhead. Static geometry is generated once from a seeded PRNG;
 * each frame interpolates the payload between 15-minute steps so motion is continuous. */
import type { CityPayload, CityScenario, Meta } from "@/lib/types";
import { at, clamp, lerp } from "@/lib/utils";

export const W = 1200;
export const H = 640;
const GROUND = 158;

type Pt = [number, number];
interface Win { x: number; y: number; w: number; h: number; r: number; region: string; cls: string }
interface Line { key: string; a: Pt; b: Pt; c?: Pt; limit: number; phase: number }
interface Puff { x: number; y: number; r: number; life: number; vx: number }

function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const mix = (a: string, b: string, t: number) => {
  const [r1, g1, b1] = hexToRgb(a); const [r2, g2, b2] = hexToRgb(b);
  return `rgb(${Math.round(lerp(r1, r2, t))},${Math.round(lerp(g1, g2, t))},${Math.round(lerp(b1, b2, t))})`;
};
const rgba = (hex: string, a: number) => { const [r, g, b] = hexToRgb(hex); return `rgba(${r},${g},${b},${a})`; };

export interface Palette {
  dark: boolean; bg: string; panel: string; raised: string; border: string; fg: string; muted: string;
  faint: string; teal: string; amber: string; danger: string; r1: string; r2: string; r3: string;
}

export function readPalette(): Palette {
  const s = getComputedStyle(document.documentElement);
  const g = (n: string) => s.getPropertyValue(n).trim();
  return {
    dark: document.documentElement.classList.contains("dark"),
    bg: g("--background"), panel: g("--panel"), raised: g("--raised"), border: g("--border"),
    fg: g("--foreground"), muted: g("--muted-foreground"), faint: g("--faint"), teal: g("--primary"),
    amber: g("--amber-fill"), danger: g("--danger"), r1: g("--r1"), r2: g("--r2"), r3: g("--r3"),
  };
}

const NODES: Record<string, Pt> = { NAT: [58, 300], R1: [292, 300], R2: [604, 300], R3: [930, 300] };
const REGION_BOX: Record<string, [number, number, number, number]> = {
  R1: [128, 350, 440, 572], R2: [462, 350, 772, 572], R3: [794, 350, 1112, 572],
};

export class CityScene {
  private ctx: CanvasRenderingContext2D;
  private windows: Win[] = [];
  private factories: { x: number; y: number; w: number; h: number }[] = [];
  private towers: { x: number; y: number; w: number; h: number }[] = [];
  private houses: { x: number; y: number; w: number; h: number; r: number }[] = [];
  private fields: { x: number; y: number; w: number; h: number; pump: Pt }[] = [];
  private stars: Pt[] = [];
  private lines: Line[] = [];
  private puffs: Record<string, Puff[]> = { G1A: [], G1B: [], G2: [] };
  private clouds: { x: number; y: number; s: number; v: number }[] = [];
  private rotor = [0, 1.3, 2.4];
  private trainX = 140;
  private data: CityPayload | null = null;
  private meta: Meta | null = null;
  private scen: CityScenario = "baseline";
  private scale = 1;
  pal: Palette;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    this.pal = readPalette();
    this.build();
  }

  onTheme() { this.pal = readPalette(); }

  setData(d: CityPayload | null, meta: Meta | null, scen: CityScenario) {
    this.data = d; this.meta = meta; this.scen = scen;
    if (meta) {
      this.lines = meta.config.interties.map((t) => ({
        key: `${t.from}-${t.to}`, a: NODES[t.from], b: NODES[t.to], limit: t.mw, phase: Math.random(),
        c: t.from === "R1" && t.to === "R3" ? [611, 352] as Pt : undefined,
      }));
      const imp = meta.config.generators.IMP?.pmax_mw ?? 90;
      this.lines.unshift({ key: "NAT-R1", a: NODES.NAT, b: NODES.R1, limit: imp, phase: 0 });
    }
  }

  resize(cssW: number) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.scale = cssW / W;
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round((cssW * H) / W * dpr);
    this.canvas.style.height = `${(cssW * H) / W}px`;
    this.ctx.setTransform(this.scale * dpr, 0, 0, this.scale * dpr, 0, 0);
  }

  private build() {
    const r = rng(20260914);
    for (let i = 0; i < 70; i++) this.stars.push([r() * W, r() * (GROUND - 20)]);
    for (let i = 0; i < 6; i++) this.clouds.push({ x: r() * W, y: 24 + r() * 70, s: 0.7 + r() * 0.8, v: 4 + r() * 6 });
    // R1 factories
    for (let i = 0; i < 6; i++) {
      const x = 146 + i * 48 + (i > 2 ? 10 : 0), w = 40, h = 30 + r() * 16, y = 470 - h;
      this.factories.push({ x, y, w, h });
      for (let c = 0; c < 4; c++) for (let k = 0; k < 2; k++)
        this.windows.push({ x: x + 5 + c * 9, y: y + 10 + k * 9, w: 5, h: 4, r: r(), region: "R1", cls: "industrial" });
    }
    // R1 worker housing
    for (let i = 0; i < 16; i++) {
      const x = 150 + (i % 8) * 34, y = 492 + Math.floor(i / 8) * 26;
      this.houses.push({ x, y, w: 22, h: 14, r: r() });
      this.windows.push({ x: x + 8, y: y + 5, w: 6, h: 5, r: r(), region: "R1", cls: "domestic" });
    }
    // R2 towers (commercial + domestic)
    let x = 470;
    while (x < 760) {
      const w = 18 + Math.floor(r() * 12), h = 70 + r() * 110, y = 560 - h;
      this.towers.push({ x, y, w, h });
      const cls = r() < 0.5 ? "commercial" : "domestic";
      for (let yy = y + 7; yy < 552; yy += 9) for (let xx = x + 4; xx < x + w - 4; xx += 6)
        this.windows.push({ x: xx, y: yy, w: 3, h: 4, r: r(), region: "R2", cls });
      x += w + 4 + Math.floor(r() * 5);
    }
    // R3 homes and fields
    for (let i = 0; i < 40; i++) {
      const col = i % 10, row = Math.floor(i / 10);
      const hx = 804 + col * 30 + (row % 2) * 12, hy = 402 + row * 26;
      this.houses.push({ x: hx, y: hy, w: 20, h: 13, r: r() });
      this.windows.push({ x: hx + 7, y: hy + 5, w: 6, h: 5, r: r(), region: "R3", cls: "domestic" });
    }
    for (let i = 0; i < 5; i++)
      this.fields.push({ x: 804 + i * 60, y: 516, w: 54, h: 42, pump: [804 + i * 60 + 27, 537] });
  }

  // ---------------------------------------------------------------- per-frame helpers
  private v(series: (number | null)[] | undefined, step: number) { return at(series, step); }

  private regionTotals(step: number, r: string) {
    const s = this.data!.scenarios[this.scen];
    let load = 0, shed = 0;
    const byCls: Record<string, [number, number]> = {};
    for (const c of Object.keys(s.load[r])) {
      const l = this.v(s.load[r][c], step), sh = this.v(s.shed[r][c], step);
      load += l; shed += sh; byCls[c] = [l, sh];
    }
    return { load, shed, byCls };
  }

  render(step: number, dt: number) {
    const ctx = this.ctx, p = this.pal;
    if (!this.data || !this.meta) { ctx.fillStyle = p.bg; ctx.fillRect(0, 0, W, H); return; }
    const d = this.data, s = d.scenarios[this.scen], gens = this.meta.config.generators;
    const cz = this.v(d.weather.cos_zenith, step);
    const csi = this.v(d.weather.csi, step);
    const wind = this.v(d.weather.wind_cf, step);
    const hour = ((step * d.dt_min) / 60) % 24;
    const daylight = clamp(cz * 3.2, 0, 1);
    const night = 1 - daylight;

    // ---- sky
    const top = p.dark ? mix("#06111f", "#1c4870", daylight) : mix("#9cb1cc", "#cfe3f5", daylight);
    const bot = p.dark ? mix("#0b1f3a", "#3d6f96", daylight) : mix("#c3d0e2", "#eef5fb", daylight);
    const g = ctx.createLinearGradient(0, 0, 0, GROUND);
    g.addColorStop(0, top); g.addColorStop(1, bot);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, GROUND);
    if (night > 0.2) {
      ctx.fillStyle = rgba("#ffffff", 0.55 * night * (p.dark ? 1 : 0.4));
      for (const [sx, sy] of this.stars) ctx.fillRect(sx, sy, 1.4, 1.4);
    }
    // sun / moon on an arc (06:00 -> 18:00)
    const sunT = (hour - 6) / 12;
    if (sunT > -0.05 && sunT < 1.05) {
      const sx = lerp(80, W - 80, sunT), sy = GROUND - 14 - Math.sin(Math.PI * clamp(sunT, 0, 1)) * 120;
      const glow = ctx.createRadialGradient(sx, sy, 2, sx, sy, 46);
      glow.addColorStop(0, rgba("#ffd27a", 0.9 * csi + 0.1)); glow.addColorStop(1, rgba("#ffd27a", 0));
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(sx, sy, 46, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#ffe3a3"; ctx.beginPath(); ctx.arc(sx, sy, 11, 0, Math.PI * 2); ctx.fill();
    } else {
      const mT = ((hour + 6) % 24) / 12;
      const mx = lerp(80, W - 80, mT), my = GROUND - 30 - Math.sin(Math.PI * clamp(mT, 0, 1)) * 90;
      ctx.fillStyle = rgba("#e8eef7", p.dark ? 0.85 : 0.6);
      ctx.beginPath(); ctx.arc(mx, my, 9, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = top; ctx.beginPath(); ctx.arc(mx + 4, my - 3, 8, 0, Math.PI * 2); ctx.fill();
    }
    // clouds, denser on overcast monsoon days
    const cover = clamp(1 - csi, 0, 1);
    for (const c of this.clouds) {
      c.x += c.v * dt * (0.4 + wind); if (c.x > W + 120) c.x = -140;
      ctx.fillStyle = rgba(p.dark ? "#9fb2c9" : "#ffffff", 0.12 + 0.55 * cover);
      for (let k = 0; k < 4; k++) {
        ctx.beginPath(); ctx.ellipse(c.x + k * 26 * c.s, c.y + (k % 2) * 6, 30 * c.s, 13 * c.s, 0, 0, Math.PI * 2); ctx.fill();
      }
    }

    // ---- ground
    ctx.fillStyle = p.dark ? mix("#0a1a30", "#11283f", daylight) : mix("#dfe6ee", "#eef2f6", daylight);
    ctx.fillRect(0, GROUND, W, H - GROUND);
    ctx.strokeStyle = rgba(p.fg, 0.08); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, GROUND + 0.5); ctx.lineTo(W, GROUND + 0.5); ctx.stroke();

    // ---- generation
    this.drawNational(step);
    this.drawCoal(step, dt, gens);
    this.drawGas(step, dt, gens);
    this.drawHydro(step, gens);
    this.drawSolar(step, gens);
    this.drawWind(step, dt, wind);

    // ---- transmission with flowing power
    this.drawLines(step, dt);

    // ---- districts
    const tot: Record<string, ReturnType<CityScene["regionTotals"]>> = {};
    for (const r of Object.keys(REGION_BOX)) tot[r] = this.regionTotals(step, r);
    this.drawDistricts(tot, night, step, dt);

    // ---- region labels
    ctx.textBaseline = "alphabetic";
    for (const [r, [x0, y0]] of Object.entries(REGION_BOX)) {
      const name = this.meta.config.regions[r]?.name ?? r;
      const t = tot[r];
      ctx.fillStyle = p.fg; ctx.font = `600 17.2px "Inter Variable", Inter, sans-serif`;
      ctx.fillText(`${r}  ${name}`, x0, y0 + 4);
      ctx.fillStyle = p.muted; ctx.font = `500 15.8px "Source Code Pro Variable", monospace`;
      const price = this.v(s.price_rt[r], step);
      ctx.fillText(`${(t.load - t.shed).toFixed(0)} MW  ₹${price.toFixed(2)}`, x0, y0 + 25);
      if (t.shed > 0.5) {
        ctx.fillStyle = p.amber; ctx.font = `600 15.8px "Inter Variable", Inter, sans-serif`;
        ctx.fillText(`Shedding ${t.shed.toFixed(0)} MW`, x0 + 168, y0 + 25);
      }
    }
    // rail line + train (traction, priority 1: never shed)
    this.drawRail(step, dt);
  }

  private drawNational(step: number) {
    const ctx = this.ctx, p = this.pal;
    const imp = this.v(this.data!.scenarios[this.scen].gen.IMP, step);
    ctx.strokeStyle = rgba(p.fg, 0.35); ctx.lineWidth = 1.2;
    for (const x of [18, 58]) {
      ctx.beginPath(); ctx.moveTo(x - 8, 300); ctx.lineTo(x, 262); ctx.lineTo(x + 8, 300);
      ctx.moveTo(x - 10, 272); ctx.lineTo(x + 10, 272); ctx.stroke();
    }
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText("National grid", 6, 246);
    ctx.font = `500 15.2px "Source Code Pro Variable", monospace`; ctx.fillStyle = p.fg;
    ctx.fillText(`${imp.toFixed(0)} MW in`, 6, 326);
  }

  private stack(x: number, y: number, h: number, key: string, out: number, pmax: number, dt: number, tripped: boolean) {
    const ctx = this.ctx, p = this.pal;
    ctx.fillStyle = tripped ? rgba(p.danger, 0.8) : p.dark ? "#2a4466" : "#9aa8ba";
    ctx.fillRect(x, y - h, 9, h);
    const arr = this.puffs[key];
    const rate = (out / pmax) * 9;
    if (Math.random() < rate * dt) arr.push({ x: x + 4.5, y: y - h, r: 4, life: 0, vx: 4 + Math.random() * 6 });
    for (let i = arr.length - 1; i >= 0; i--) {
      const q = arr[i];
      q.life += dt; q.y -= 14 * dt; q.x += q.vx * dt; q.r += 6 * dt;
      if (q.life > 3.2) { arr.splice(i, 1); continue; }
      ctx.fillStyle = rgba(p.dark ? "#b8c6d8" : "#8c99aa", 0.32 * (1 - q.life / 3.2));
      ctx.beginPath(); ctx.arc(q.x, q.y, q.r, 0, Math.PI * 2); ctx.fill();
    }
  }

  private plantBody(x: number, y: number, w: number, h: number, label: string, value: string, off = false) {
    const ctx = this.ctx, p = this.pal;
    ctx.fillStyle = p.dark ? "#16304f" : "#c8d3e0";
    ctx.fillRect(x, y - h, w, h);
    ctx.strokeStyle = off ? p.danger : rgba(p.fg, 0.18); ctx.lineWidth = off ? 1.5 : 1;
    ctx.strokeRect(x + 0.5, y - h + 0.5, w - 1, h - 1);
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText(label, x, y + 20);
    ctx.fillStyle = off ? p.danger : p.fg; ctx.font = `500 15.2px "Source Code Pro Variable", monospace`;
    ctx.fillText(value, x, y + 39);
  }

  private drawCoal(step: number, dt: number, gens: Meta["config"]["generators"]) {
    const s = this.data!.scenarios[this.scen];
    const a = this.v(s.gen.G1A, step), b = this.v(s.gen.G1B, step);
    const bOff = b < 1 && (this.meta!.weeks.stress.outages.length > 0);
    this.plantBody(176, 250, 92, 34, "Coal G1A + G1B", bOff ? `${a.toFixed(0)} MW, G1B out` : `${(a + b).toFixed(0)} MW`, bOff);
    this.stack(196, 216, 46, "G1A", a, gens.G1A.pmax_mw, dt, false);
    this.stack(232, 216, 46, "G1B", b, gens.G1B.pmax_mw, dt, bOff);
    this.feed([222, 250], NODES.R1);
  }

  private drawGas(step: number, dt: number, gens: Meta["config"]["generators"]) {
    const v = this.v(this.data!.scenarios[this.scen].gen.G2, step);
    this.plantBody(560, 250, 70, 26, "Gas G2", `${v.toFixed(0)} MW`);
    this.stack(610, 224, 22, "G2", v, gens.G2.pmax_mw, dt, false);
    this.feed([595, 250], NODES.R2);
  }

  private drawHydro(step: number, gens: Meta["config"]["generators"]) {
    const ctx = this.ctx, p = this.pal;
    const v = this.v(this.data!.scenarios[this.scen].gen.H1, step);
    ctx.fillStyle = rgba(p.r1, 0.35);
    ctx.fillRect(772, 222, 44, 28);
    ctx.fillStyle = p.dark ? "#1d3a5e" : "#b5c3d4";
    ctx.beginPath(); ctx.moveTo(816, 214); ctx.lineTo(826, 214); ctx.lineTo(836, 250); ctx.lineTo(816, 250); ctx.fill();
    const flow = v / gens.H1.pmax_mw;
    ctx.strokeStyle = rgba("#7cc4ff", 0.25 + 0.6 * flow); ctx.lineWidth = 1 + 2 * flow;
    ctx.beginPath(); ctx.moveTo(836, 244); ctx.lineTo(852, 250); ctx.stroke();
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText("Hydro H1", 772, 270);
    ctx.fillStyle = p.fg; ctx.font = `500 15.2px "Source Code Pro Variable", monospace`;
    ctx.fillText(`${v.toFixed(0)} MW`, 772, 289);
    this.feed([826, 250], NODES.R3);
  }

  private drawSolar(step: number, gens: Meta["config"]["generators"]) {
    const ctx = this.ctx, p = this.pal;
    const v = this.v(this.data!.scenarios[this.scen].gen.S1, step);
    const f = v / gens.S1.pmax_mw;
    for (let r = 0; r < 3; r++) for (let c = 0; c < 6; c++) {
      const x = 876 + c * 17, y = 216 + r * 11;
      ctx.fillStyle = mix(p.dark ? "#1b3354" : "#8fa6c2", "#5fb7ff", f);
      ctx.fillRect(x, y, 14, 8);
    }
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText("Solar S1", 876, 270);
    ctx.fillStyle = p.fg; ctx.font = `500 15.2px "Source Code Pro Variable", monospace`;
    ctx.fillText(`${v.toFixed(0)} MW`, 876, 289);
    this.feed([926, 250], NODES.R3);
  }

  private drawWind(step: number, dt: number, windCf: number) {
    const ctx = this.ctx, p = this.pal;
    const v = this.v(this.data!.scenarios[this.scen].gen.W1, step);
    [1010, 1060, 1110].forEach((x, i) => {
      const top = 186 - i * 4;
      ctx.strokeStyle = p.dark ? "#9fb3cc" : "#6b7c92"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x, 250); ctx.lineTo(x, top); ctx.stroke();
      this.rotor[i] += dt * (0.6 + windCf * 7);
      ctx.lineWidth = 1.6;
      for (let k = 0; k < 3; k++) {
        const a = this.rotor[i] + (k * Math.PI * 2) / 3;
        ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x + Math.cos(a) * 22, top + Math.sin(a) * 22); ctx.stroke();
      }
    });
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText("Wind W1", 1010, 270);
    ctx.fillStyle = p.fg; ctx.font = `500 15.2px "Source Code Pro Variable", monospace`;
    ctx.fillText(`${v.toFixed(0)} MW`, 1010, 289);
    this.feed([1060, 250], NODES.R3);
  }

  private feed(a: Pt, b: Pt) {
    const ctx = this.ctx;
    ctx.strokeStyle = rgba(this.pal.fg, 0.16); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
  }

  private pointOn(l: Line, t: number): Pt {
    if (!l.c) return [lerp(l.a[0], l.b[0], t), lerp(l.a[1], l.b[1], t)];
    const u = 1 - t;
    return [u * u * l.a[0] + 2 * u * t * l.c[0] + t * t * l.b[0], u * u * l.a[1] + 2 * u * t * l.c[1] + t * t * l.b[1]];
  }

  private drawLines(step: number, dt: number) {
    const ctx = this.ctx, p = this.pal;
    const s = this.data!.scenarios[this.scen];
    for (const l of this.lines) {
      const flow = l.key === "NAT-R1" ? this.v(s.gen.IMP, step) : this.v(s.flow[l.key], step);
      const load = Math.abs(flow) / l.limit;
      const col = load > 0.98 ? p.danger : load > 0.75 ? p.amber : p.teal;
      ctx.strokeStyle = rgba(p.fg, 0.22); ctx.lineWidth = 2.2;
      ctx.beginPath(); ctx.moveTo(l.a[0], l.a[1]);
      if (l.c) ctx.quadraticCurveTo(l.c[0], l.c[1], l.b[0], l.b[1]); else ctx.lineTo(l.b[0], l.b[1]);
      ctx.stroke();
      // particles: count and speed follow |MW|, direction follows sign
      const len = Math.hypot(l.b[0] - l.a[0], l.b[1] - l.a[1]);
      l.phase = (l.phase + dt * (0.08 + load * 0.5) * (flow >= 0 ? 1 : -1) * (300 / len) + 1) % 1;
      const n = Math.max(2, Math.round(len / 34));
      ctx.fillStyle = col;
      for (let k = 0; k < n; k++) {
        if (Math.abs(flow) < 0.5) break;
        const [x, y] = this.pointOn(l, (k / n + l.phase) % 1);
        ctx.beginPath(); ctx.arc(x, y, 1.6 + load * 1.8, 0, Math.PI * 2); ctx.fill();
      }
      const [mx, my] = this.pointOn(l, 0.5);
      ctx.fillStyle = load > 0.98 ? p.danger : p.muted;
      ctx.font = `500 14.5px "Source Code Pro Variable", monospace`;
      ctx.fillText(`${Math.abs(flow).toFixed(0)}/${l.limit} MW`, mx - 30, l.c ? my - 8 : my + 20);
    }
    for (const [k, [x, y]] of Object.entries(NODES)) {
      if (k === "NAT") continue;
      ctx.fillStyle = p.dark ? "#0c1f3a" : "#ffffff";
      ctx.strokeStyle = p.fg; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.rect(x - 7, y - 7, 14, 14); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x - 3, y); ctx.lineTo(x + 3, y); ctx.stroke();
    }
  }

  private drawDistricts(tot: Record<string, ReturnType<CityScene["regionTotals"]>>, night: number,
    step: number, dt: number) {
    const ctx = this.ctx, p = this.pal;
    const body = p.dark ? "#13294b" : "#c9d4e2";
    const body2 = p.dark ? "#183258" : "#b8c6d8";
    for (const f of this.factories) {
      ctx.fillStyle = body; ctx.fillRect(f.x, f.y, f.w, f.h);
      ctx.fillStyle = body2;
      ctx.beginPath(); ctx.moveTo(f.x, f.y);
      for (let k = 0; k < 4; k++) { ctx.lineTo(f.x + k * 10 + 10, f.y - 8); ctx.lineTo(f.x + k * 10 + 10, f.y); }
      ctx.fill();
    }
    for (const t of this.towers) { ctx.fillStyle = body; ctx.fillRect(t.x, t.y, t.w, t.h); }
    for (const h of this.houses) {
      ctx.fillStyle = body; ctx.fillRect(h.x, h.y, h.w, h.h);
      ctx.fillStyle = body2; ctx.beginPath();
      ctx.moveTo(h.x - 2, h.y); ctx.lineTo(h.x + h.w / 2, h.y - 7); ctx.lineTo(h.x + h.w + 2, h.y); ctx.fill();
    }
    // windows: lit unless this class is being shed in that region
    const lit = rgba("#ffcf6e", 0.35 + 0.6 * night);
    const litDay = p.dark ? "#2b4b73" : "#e9f0f7";
    const dark = p.dark ? "#081628" : "#8898ad";
    for (const w of this.windows) {
      const c = tot[w.region].byCls[w.cls];
      const shedFrac = c && c[0] > 0 ? c[1] / c[0] : 0;
      const on = w.r >= shedFrac;
      ctx.fillStyle = !on ? dark : night > 0.25 ? lit : litDay;
      ctx.fillRect(w.x, w.y, w.w, w.h);
    }
    // irrigation fields + pumps (shed first when supply is short)
    const irr = tot.R3.byCls.irrigation;
    const irrOn = irr ? (irr[0] - irr[1]) / Math.max(this.meta!.config.regions.R3.peak_mw.irrigation, 1) : 0;
    const time = step * 0.9;
    for (const f of this.fields) {
      ctx.fillStyle = p.dark ? "#10301f" : "#cfe3cf";
      ctx.fillRect(f.x, f.y, f.w, f.h);
      ctx.strokeStyle = rgba(p.r3, 0.35); ctx.lineWidth = 1;
      for (let k = 6; k < f.h; k += 7) { ctx.beginPath(); ctx.moveTo(f.x + 3, f.y + k); ctx.lineTo(f.x + f.w - 3, f.y + k); ctx.stroke(); }
      if (irrOn > 0.05) {
        ctx.strokeStyle = rgba("#7cc4ff", 0.35 + 0.5 * irrOn); ctx.lineWidth = 1.2;
        for (let k = 0; k < 3; k++) {
          const rr = ((time * 2 + k / 3 + dt) % 1) * 14 * irrOn + 3;
          ctx.beginPath(); ctx.arc(f.pump[0], f.pump[1], rr, Math.PI * 1.1, Math.PI * 1.9); ctx.stroke();
        }
      }
      ctx.fillStyle = irrOn > 0.05 ? "#7cc4ff" : p.faint;
      ctx.beginPath(); ctx.arc(f.pump[0], f.pump[1], 2.5, 0, Math.PI * 2); ctx.fill();
    }
    // shedding wash over a region
    for (const [r, [x0, y0, x1, y1]] of Object.entries(REGION_BOX)) {
      const t = tot[r];
      const frac = t.load > 0 ? t.shed / t.load : 0;
      if (frac > 0.005) {
        ctx.fillStyle = rgba(p.amber, 0.05 + frac * 0.35);
        ctx.fillRect(x0 - 8, y0 + 26, x1 - x0 + 16, y1 - y0 - 26);
      }
    }
  }

  private drawRail(step: number, dt: number) {
    const ctx = this.ctx, p = this.pal;
    const s = this.data!.scenarios[this.scen];
    const traction = this.v(s.load.R1.traction, step) + this.v(s.load.R2.traction, step);
    const y = 592;
    ctx.strokeStyle = rgba(p.fg, 0.3); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(120, y); ctx.lineTo(780, y); ctx.moveTo(120, y + 5); ctx.lineTo(780, y + 5); ctx.stroke();
    this.trainX += dt * (40 + traction * 2.2);
    if (this.trainX > 800) this.trainX = 60;
    ctx.fillStyle = p.r1;
    for (let k = 0; k < 4; k++) {
      const x = this.trainX - k * 26;
      if (x > 118 && x < 782) ctx.fillRect(x, y - 11, 23, 10);
    }
    ctx.fillStyle = p.muted; ctx.font = `500 15.2px "Inter Variable", Inter, sans-serif`;
    ctx.fillText(`Railway traction ${traction.toFixed(0)} MW, never shed`, 128, y + 30);
  }
}
