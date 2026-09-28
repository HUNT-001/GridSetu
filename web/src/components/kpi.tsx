import { useEffect, useRef } from "react";
import gsap from "gsap";
import { cn, prefersReducedMotion } from "@/lib/utils";

/** Number that tweens to its new value (GSAP) when data changes, e.g. after a scenario
 *  run lands. Text is written straight to the node: no React renders per frame. */
export function AnimatedNumber({ value, format, className }: {
  value: number; format: (v: number) => string; className?: string;
}) {
  const el = useRef<HTMLSpanElement>(null);
  const cur = useRef({ v: value });
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    if (prefersReducedMotion()) { cur.current.v = value; node.textContent = format(value); return; }
    const t = gsap.to(cur.current, {
      v: value, duration: 0.6, ease: "power3.out",
      onUpdate: () => { node.textContent = format(cur.current.v); },
    });
    return () => { t.kill(); };
  }, [value, format]);
  return <span ref={el} className={cn("num", className)}>{format(cur.current.v)}</span>;
}

export function Kpi({ label, value, unit, format, baseline, better = "lower", hint, className }: {
  label: string; value: number; unit?: string; format: (v: number) => string; baseline?: number;
  better?: "lower" | "higher"; hint?: string; className?: string;
}) {
  let delta: string | null = null;
  let good = false;
  if (baseline !== undefined && baseline !== 0) {
    const c = ((value - baseline) / Math.abs(baseline)) * 100;
    good = better === "lower" ? c < 0 : c > 0;
    delta = `${c > 0 ? "+" : c < 0 ? "−" : ""}${Math.abs(c).toFixed(0)}%`;
  }
  return (
    <div className={cn("min-w-0", className)}>
      <div className="truncate text-[12.5px] text-muted-foreground" title={hint}>{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <AnimatedNumber value={value} format={format} className="text-[26px] font-medium leading-none tracking-tight" />
        {unit && <span className="text-[12.5px] text-muted-foreground">{unit}</span>}
      </div>
      {baseline !== undefined && (
        <div className="mt-1.5 text-[12px] text-muted-foreground">
          <span className={cn("num font-medium", delta && (good ? "text-primary" : "text-amber"))}>{delta}</span>
          <span> vs baseline <span className="num">{format(baseline)}</span></span>
        </div>
      )}
    </div>
  );
}
