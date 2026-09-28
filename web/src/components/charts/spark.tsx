import { memo } from "react";

/** Tiny SVG sparkline for table rows (no canvas, no library). */
export const Sparkline = memo(function Sparkline({ values, width = 84, height = 22, color = "var(--primary)" }: {
  values: number[]; width?: number; height?: number; color?: string;
}) {
  if (!values.length) return null;
  const max = Math.max(...values, 1e-6);
  const min = Math.min(...values, 0);
  const pts = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * (width - 2) + 1;
    const y = height - 1 - ((v - min) / (max - min || 1)) * (height - 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
});

/** Paired horizontal bars: baseline vs GridSetu, width animates in 140 ms. */
export function PairBar({ baseline, gridsetu, max, fmt, labels = ["Baseline", "GridSetu"] }: {
  baseline: number; gridsetu: number; max: number; fmt: (v: number) => string; labels?: [string, string];
}) {
  const w = (v: number) => `${Math.max(0.5, (v / (max || 1)) * 100)}%`;
  return (
    <div className="space-y-1.5">
      {([[labels[0], baseline, "var(--series-baseline)"], [labels[1], gridsetu, "var(--series-gridsetu)"]] as const)
        .map(([label, v, c]) => (
          <div key={label} className="grid grid-cols-[80px_1fr_72px] items-center gap-2 text-[12px]">
            <span className="text-muted-foreground">{label}</span>
            <div className="h-2 rounded-full bg-raised">
              <div className="h-2 rounded-full transition-[width] duration-150 ease-[var(--ease-snap)]"
                style={{ width: w(v), background: c }} />
            </div>
            <span className="num text-right">{fmt(v)}</span>
          </div>
        ))}
    </div>
  );
}
