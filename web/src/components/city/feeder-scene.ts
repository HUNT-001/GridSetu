/* Pilot feeder F07 inset: the same 420 households under the baseline and under GridSetu,
 * side by side. Each house eases towards its state (supplied, Tier-3 curtailed, dark) in
 * ~120 ms, so step changes read as a continuous dimming instead of a flicker. */
import type { FeederPayload, Variant } from "@/lib/types";
import { at, clamp, decodeB64 } from "@/lib/utils";
import { readPalette, type Palette } from "./scene";

export const FW = 660;
export const FH = 372;
const COLS = 21;
const CELL = 12;

const rgba = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

interface Panel { variant: Variant; x: number; status: Uint8Array | null; cur: Float32Array; cur3: Float32Array }

export class FeederScene {
  private ctx: CanvasRenderingContext2D;
  private panels: Panel[] = [];
  private data: FeederPayload | null = null;
  private nHh = 420;
  intro = 1;
  pal: Palette;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    this.pal = readPalette();
  }

  setData(d: FeederPayload | null, right: Variant) {
    this.data = d;
    if (!d) return;
    this.nHh = d.n_households;
    const mk = (variant: Variant, x: number): Panel => ({
      variant, x, status: d.variants[variant] ? decodeB64(d.variants[variant].hh_status_b64) : null,
      cur: new Float32Array(this.nHh).fill(1), cur3: new Float32Array(this.nHh),
    });
    const keep = this.panels;
    this.panels = [mk("baseline", 18), mk(right, 342)];
    // keep eased brightness across data swaps so a scenario change fades rather than jumps
    if (keep.length === 2) { this.panels[0].cur.set(keep[0].cur); this.panels[1].cur.set(keep[1].cur); }
  }

  resize(cssW: number) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const s = cssW / FW;
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round(cssW * (FH / FW) * dpr);
    this.canvas.style.height = `${cssW * (FH / FW)}px`;
    this.ctx.setTransform(s * dpr, 0, 0, s * dpr, 0, 0);
  }

  render(step: number, dt: number, night: number) {
    const ctx = this.ctx, p = this.pal, d = this.data;
    ctx.fillStyle = p.panel; ctx.fillRect(0, 0, FW, FH);
    if (!d) return;
    const i = clamp(Math.floor(step), 0, d.n - 1);
    const k = 1 - Math.exp(-dt / 0.12);
    for (const pn of this.panels) {
      const v = d.variants[pn.variant];
      if (!v || !pn.status) continue;
      const state = d.state_codes[v.state[i]] ?? "normal";
      const tripped = state.includes("trip") && state !== "overload_event";
      const title = pn.variant === "baseline" ? "Baseline feeder" : "With GridSetu";
      ctx.fillStyle = p.fg; ctx.font = `600 14px "Inter Variable", Inter, sans-serif`;
      ctx.textBaseline = "alphabetic";
      ctx.fillText(title, pn.x, 22);
      const lit = v.hh_lit_pct[i] ?? 100;
      ctx.fillStyle = tripped ? p.danger : p.muted;
      ctx.font = `500 12px "Inter Variable", Inter, sans-serif`;
      ctx.fillText(tripped ? "Feeder dark" : `${lit.toFixed(0)}% of homes fully supplied`, pn.x, 40);

      // houses
      const off = i * this.nHh;
      const litCol = night > 0.3 ? "#ffc861" : p.dark ? "#d6b77a" : "#e3a23a";
      for (let h = 0; h < this.nHh; h++) {
        const s = pn.status[off + h];
        const introOn = h / this.nHh < this.intro;
        const target = !introOn ? 0 : s === 0 ? 1 : s === 1 ? 0.55 : 0;
        pn.cur[h] += (target - pn.cur[h]) * k;
        pn.cur3[h] += ((s === 1 ? 1 : 0) - pn.cur3[h]) * k;
        const col = h % COLS, row = Math.floor(h / COLS);
        const x = pn.x + col * CELL, y = 54 + row * CELL;
        ctx.fillStyle = p.dark ? "#0a1a31" : "#d5dde8";
        ctx.fillRect(x, y, CELL - 3, CELL - 3);
        const b = pn.cur[h];
        if (b > 0.02) { ctx.fillStyle = rgba(litCol, b); ctx.fillRect(x, y, CELL - 3, CELL - 3); }
        if (pn.cur3[h] > 0.05) {
          ctx.strokeStyle = rgba(p.teal, pn.cur3[h]); ctx.lineWidth = 1.2;
          ctx.strokeRect(x + 0.6, y + 0.6, CELL - 4.2, CELL - 4.2);
        }
      }

      // critical loads (Tier 1)
      const t1u = at(v.series.tier1_unserved, step);
      const t1on = t1u < 0.01;
      const y0 = 54 + Math.ceil(this.nHh / COLS) * CELL + 12;
      const items: [string, string][] = [["Clinic", "+"], ["School", "S"], ["Pump", "P"], ["Lights", "L"]];
      items.forEach(([label, glyph], j) => {
        const x = pn.x + j * 64;
        ctx.fillStyle = t1on ? rgba(p.teal, 0.9) : p.dark ? "#0a1a31" : "#c3cdd9";
        ctx.fillRect(x, y0, 22, 22);
        ctx.fillStyle = t1on ? p.panel : p.faint;
        ctx.font = `700 13px "Inter Variable", Inter, sans-serif`;
        ctx.fillText(glyph, x + (glyph === "+" ? 6.5 : 6.5), y0 + 16);
        ctx.fillStyle = p.muted; ctx.font = `500 10.5px "Inter Variable", Inter, sans-serif`;
        ctx.fillText(label, x, y0 + 36);
      });
      // import meter + battery
      const imp = tripped ? 0 : Math.max(0, at(v.series.import, step));
      const soc = at(v.series.soc_pct, step);
      const bat = at(v.series.battery_kw, step);
      const bx = pn.x + 262, by = y0 - 2;
      if (pn.variant !== "baseline") {
        ctx.strokeStyle = p.fg; ctx.lineWidth = 1.2; ctx.strokeRect(bx, by, 36, 16);
        ctx.fillRect(bx + 36, by + 5, 3, 6);
        ctx.fillStyle = soc < 25 ? p.amber : p.teal;
        ctx.fillRect(bx + 2, by + 2, (32 * clamp(soc, 0, 100)) / 100, 12);
        ctx.fillStyle = p.muted; ctx.font = `500 10.5px "Source Code Pro Variable", monospace`;
        ctx.fillText(`${soc.toFixed(0)}% ${bat > 1 ? "out" : bat < -1 ? "in" : ""}`, bx, by + 30);
      }
      ctx.fillStyle = tripped ? p.faint : p.fg; ctx.font = `500 12px "Source Code Pro Variable", monospace`;
      ctx.textAlign = "right";
      ctx.fillText(`${imp.toFixed(0)} kW from grid`, pn.x + COLS * CELL - 3, 22);
      ctx.textAlign = "left";
    }
    // divider
    ctx.strokeStyle = p.border; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(FW / 2, 10); ctx.lineTo(FW / 2, FH - 10); ctx.stroke();
  }
}
