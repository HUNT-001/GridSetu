import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useUI } from "@/lib/store";
import { cn } from "@/lib/utils";

export interface ChartSeries {
  label: string;
  values: (number | null)[];
  color: string;            // CSS variable ("--series-gridsetu"), with optional alpha ("--x/0.3"), or a colour
  width?: number;
  dash?: number[];
  fill?: string;            // CSS colour for area fill under the line
  stepped?: boolean;
  unit?: string;
}

interface Props {
  series: ChartSeries[];
  height?: number;
  x?: number[];                              // default: 0..n-1 simulation steps
  xKind?: "steps" | "seconds";
  stepsPerDay?: number;
  t0?: string;
  yLabel?: string;
  yMin?: number;
  yMax?: number;
  refLines?: { y: number; label: string }[];
  shade?: { mask: boolean[]; color: string; label: string }[];
  band?: { lower: number; upper: number; color: string };   // indexes into series
  playhead?: boolean;
  syncKey?: string;
  className?: string;
  ariaLabel: string;
  valueFormat?: (v: number) => string;
  tooltipValues?: (number | null)[][];      // shown in the tooltip instead of plotted values (stacks)
}

/** Resolve "--var" or "--var/0.2" (with alpha) to a canvas colour. */
export function css(name: string): string {
  if (!name.startsWith("--")) return name;
  const [v, a] = name.split("/");
  const hex = getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#888888";
  if (!a) return hex;
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Canvas time-series chart (uPlot): fast for thousands of points, cursor synced across
 *  charts, a playhead that follows the global clock without React re-renders, and
 *  click-to-seek. */
export function TimeChart({
  series, height = 220, x, xKind = "steps", stepsPerDay = 96, t0, yLabel, yMin, yMax, refLines,
  shade, band, playhead = true, syncKey = "gs", className, ariaLabel, valueFormat, tooltipValues,
}: Props) {
  const placeRef = useRef<(() => void) | null>(null);
  const rawRef = useRef(tooltipValues);
  rawRef.current = tooltipValues;
  const wrap = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const theme = useUI((s) => s.theme);
  const seek = useUI((s) => s.seek);
  const xs = useMemo(() => x ?? series[0]?.values.map((_, i) => i) ?? [], [x, series]);
  const shape = series.map((s) => `${s.label}|${s.color}|${s.fill ?? ""}`).join(";") + `|${band?.lower}|${!!shade}`;
  const startDow = t0 ? (new Date(`${t0}Z`).getUTCDay() + 6) % 7 : 0;
  const fmt = valueFormat ?? ((v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)));

  // build / rebuild when the shape or theme changes
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ink = css("--muted-foreground");
    const grid = css("--grid");
    const font = `12px "Inter Variable", Inter, sans-serif`;
    const drawHooks: ((u: uPlot) => void)[] = [];
    if (shade?.length) {
      drawHooks.push((u) => {
        const ctx = u.ctx;
        for (const s of shade) {
          ctx.fillStyle = css(s.color);
          let start = -1;
          for (let i = 0; i <= s.mask.length; i++) {
            const on = i < s.mask.length && s.mask[i];
            if (on && start < 0) start = i;
            if (!on && start >= 0) {
              const a = u.valToPos(xs[start], "x", true);
              const b = u.valToPos(xs[Math.min(i, xs.length - 1)], "x", true);
              ctx.fillRect(a, u.bbox.top, Math.max(1, b - a), u.bbox.height);
              start = -1;
            }
          }
        }
      });
    }
    if (refLines?.length) {
      drawHooks.push((u) => {
        const ctx = u.ctx;
        ctx.save();
        ctx.strokeStyle = css("--foreground");
        ctx.globalAlpha = 0.55;
        ctx.setLineDash([5, 4]);
        ctx.lineWidth = 1 * devicePixelRatio;
        ctx.font = `${11 * devicePixelRatio}px "Inter Variable", Inter, sans-serif`;
        ctx.fillStyle = css("--foreground");
        for (const r of refLines) {
          const y = u.valToPos(r.y, "y", true);
          ctx.beginPath(); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke();
          ctx.fillText(r.label, u.bbox.left + 6 * devicePixelRatio, y - 4 * devicePixelRatio);
        }
        ctx.restore();
      });
    }
    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height,
      pxAlign: 0,
      cursor: {
        sync: { key: syncKey, setSeries: false },
        points: { size: 7, fill: (_u, i) => css(series[i - 1]?.color ?? "--foreground") },
        drag: { x: false, y: false },
        y: false,
      },
      legend: { show: false },
      scales: {
        x: { time: false },
        y: { range: (_u, lo, hi) => [yMin ?? Math.min(0, lo), yMax ?? (hi <= 0 ? 1 : hi * 1.08)] },
      },
      axes: [
        {
          stroke: ink, font, grid: { stroke: grid, width: 1 }, ticks: { show: false }, gap: 6, size: 30,
          splits: xKind === "steps"
            ? (_u, _ai, lo, hi) => {
                const out: number[] = [];
                for (let d = Math.ceil(lo / stepsPerDay) * stepsPerDay; d <= hi; d += stepsPerDay) out.push(d);
                return out;
              }
            : undefined,
          values: xKind === "steps"
            ? (_u, vals) => vals.map((v) => DAYS[(startDow + Math.round(v / stepsPerDay)) % 7])
            : (_u, vals) => vals.map((v) => `${v}s`),
        },
        {
          stroke: ink, font, grid: { stroke: grid, width: 1 }, ticks: { show: false }, gap: 6, size: 46,
          label: yLabel, labelFont: font, labelSize: 16,
          values: (_u, vals) => vals.map((v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${+v.toFixed(2)}`)),
        },
      ],
      series: [
        {},
        ...series.map((s) => ({
          label: s.label,
          stroke: css(s.color),
          width: s.width ?? 1.75,
          dash: s.dash,
          fill: s.fill ? css(s.fill) : undefined,
          points: { show: false },
          paths: s.stepped ? uPlot.paths.stepped!({ align: 1 }) : undefined,
          spanGaps: false,
        })),
      ],
      bands: band ? [{ series: [band.upper + 1, band.lower + 1], fill: css(band.color) }] : undefined,
      hooks: {
        drawClear: drawHooks,
        setSize: [() => placeRef.current?.()],
        ready: [() => placeRef.current?.()],
        setCursor: [
          (u) => {
            const tip = tipRef.current;
            const idx = u.cursor.idx;
            if (!tip) return;
            if (idx == null || u.cursor.left == null || u.cursor.left < 0) { tip.style.opacity = "0"; return; }
            const rows = series.map((s, i) => {
              const v = rawRef.current ? rawRef.current[i]?.[idx] : u.data[i + 1][idx];
              return `<div style="display:flex;gap:8px;align-items:center;justify-content:space-between">
                <span style="display:flex;align-items:center;gap:6px"><i style="width:8px;height:2px;background:${css(s.color)};display:inline-block"></i>${s.label}</span>
                <b class="num" style="font-weight:500">${v == null ? "–" : fmt(v as number)}${s.unit ? ` ${s.unit}` : ""}</b></div>`;
            }).join("");
            let head = "";
            if (xKind === "steps" && t0) {
              const d = new Date(Date.parse(`${t0}Z`) + xs[idx] * 15 * 60_000);
              head = `${DAYS[(d.getUTCDay() + 6) % 7]} ${d.getUTCDate()}, ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
            } else head = `${xs[idx].toFixed(2)} s`;
            tip.innerHTML = `<div style="color:var(--muted-foreground);margin-bottom:3px" class="num">${head}</div>${rows}`;
            const left = u.cursor.left + u.bbox.left / devicePixelRatio;
            const w = tip.offsetWidth;
            const x0 = left + 14 + w > el.clientWidth ? left - w - 14 : left + 14;
            tip.style.transform = `translate(${x0}px, 8px)`;
            tip.style.opacity = "1";
          },
        ],
      },
    };
    const data = [xs, ...series.map((s) => s.values)] as uPlot.AlignedData;
    const u = new uPlot(opts, data, el);
    plotRef.current = u;
    const ro = new ResizeObserver(() => u.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    const onClick = () => {
      if (xKind !== "steps") return;
      const idx = u.cursor.idx;
      if (idx != null) seek(xs[idx]);
    };
    u.over.addEventListener("click", onClick);
    return () => { ro.disconnect(); u.over.removeEventListener("click", onClick); u.destroy(); plotRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape, theme, height, xKind, yMin, yMax, yLabel]);

  // cheap data refresh (same shape): no rebuild, no flicker
  useEffect(() => {
    plotRef.current?.setData([xs, ...series.map((s) => s.values)] as uPlot.AlignedData, true);
  }, [series, xs]);

  // playhead follows the global clock transiently (no React renders)
  useEffect(() => {
    if (!playhead || xKind !== "steps") return;
    const place = (step: number) => {
      const u = plotRef.current;
      const h = headRef.current;
      if (!u || !h) return;
      const left = u.valToPos(step, "x") + u.bbox.left / devicePixelRatio;
      h.style.transform = `translateX(${left}px)`;
      h.style.height = `${u.bbox.height / devicePixelRatio}px`;
      h.style.top = `${u.bbox.top / devicePixelRatio}px`;
    };
    placeRef.current = () => place(useUI.getState().step);
    place(useUI.getState().step);
    const raf = requestAnimationFrame(() => place(useUI.getState().step));
    const unsub = useUI.subscribe((s) => place(s.step));
    return () => { cancelAnimationFrame(raf); unsub(); placeRef.current = null; };
  }, [playhead, xKind, shape]);

  return (
    <div className={cn("relative select-none", className)} role="img" aria-label={ariaLabel}>
      <div ref={wrap} className="w-full" />
      {playhead && xKind === "steps" && (
        <div ref={headRef} aria-hidden
          className="pointer-events-none absolute left-0 w-px bg-amber-fill/90 will-change-transform" />
      )}
      <div ref={tipRef} aria-hidden
        className="pointer-events-none absolute left-0 top-0 z-10 min-w-40 rounded-md border bg-raised/95 px-2.5 py-2 text-[12px] leading-5 opacity-0 shadow-lg backdrop-blur transition-opacity duration-100" />
    </div>
  );
}

const cssColor = (c: string) => {
  const [v, a] = c.split("/");
  return a ? `color-mix(in oklab, var(${v}) ${Number(a) * 100}%, transparent)` : `var(${v})`;
};

export function Legend({ items }: { items: { label: string; color: string; dash?: boolean; area?: boolean }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <i className={cn("inline-block", i.area ? "h-2.5 w-3 rounded-[2px]" : "h-0.5 w-3.5")}
            style={{ background: i.dash ? "transparent" : cssColor(i.color), borderTop: i.dash ? `2px dashed ${cssColor(i.color)}` : undefined }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
