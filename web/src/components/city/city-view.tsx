import { useEffect, useMemo, useRef } from "react";
import gsap from "gsap";
import { useCity, useFeeder, useMeta } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { fmtDay, fmtHM, isDark, stepDate, STATE_LABEL } from "@/lib/format";
import { at, clamp, prefersReducedMotion } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { CityScene, readPalette } from "./scene";
import { FeederScene } from "./feeder-scene";

/** Drives a canvas scene from the global playhead: one rAF loop, paused when the canvas
 *  is off screen or the tab is hidden. React only re-renders the HTML overlay, and only
 *  when the 15-minute step changes. */
function useCanvasLoop(
  ref: React.RefObject<HTMLCanvasElement | null>,
  make: (c: HTMLCanvasElement) => { render: (step: number, dt: number) => void; resize: (w: number) => void; onTheme: () => void },
  deps: unknown[],
) {
  const sceneRef = useRef<ReturnType<typeof make> | null>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const scene = make(c);
    sceneRef.current = scene;
    const parent = c.parentElement!;
    const ro = new ResizeObserver(() => scene.resize(parent.clientWidth));
    ro.observe(parent);
    scene.resize(parent.clientWidth);
    let visible = true;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0 });
    io.observe(c);
    let raf = 0, last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (visible && !document.hidden) scene.render(useUI.getState().step, dt);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const unsubTheme = useUI.subscribe((s, prev) => { if (s.theme !== prev.theme) scene.onTheme(); });
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); unsubTheme(); sceneRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return sceneRef;
}

export function CityView() {
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: meta } = useMeta();
  const { data: city } = useCity(week);
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useCanvasLoop(canvas, (c) => new CityScene(c), []);

  useEffect(() => { (scene.current as CityScene | null)?.setData(city ?? null, meta ?? null, scen); },
    [city, meta, scen, scene]);

  return (
    <div className="relative overflow-hidden rounded-lg border bg-background">
      <canvas ref={canvas} className="block w-full" aria-label="Animated city grid: generation, transmission and districts" role="img" />
      {!city && <Skeleton className="absolute inset-0 rounded-none" />}
      <CityHud />
    </div>
  );
}

function CityHud() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  if (!city) return null;
  const d = stepDate(city.t0, city.dt_min, step);
  const events = city.scenarios[scen].events.filter((e) => e.step <= step && step - e.step < 8);
  return (
    <>
      <div className="pointer-events-none absolute right-4 top-3 text-right">
        <div className="font-display text-[clamp(20px,4.2vw,34px)] leading-none tracking-tight">{fmtHM(d)}</div>
        <div className="mt-1 hidden text-[12.5px] text-muted-foreground sm:block">{fmtDay(d)}, {week === "stress" ? "stress week" : "normal week"}</div>
      </div>
      <div className="pointer-events-none absolute bottom-3 right-4 hidden max-w-[60%] flex-col items-end gap-1.5 sm:flex">
        {events.map((e) => (
          <div key={`${e.step}-${e.kind}`}
            className="animate-in rounded-md border bg-panel/90 px-2.5 py-1 text-[12.5px] shadow-sm backdrop-blur">
            <span className={e.kind === "outage" || e.kind === "shedding" ? "text-amber" : "text-muted-foreground"}>
              {e.label}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

export function FeederInset() {
  const week = useUI((s) => s.week);
  const variant = useUI((s) => s.variant);
  const { data: feeder } = useFeeder(week);
  const { data: city } = useCity(week);
  const canvas = useRef<HTMLCanvasElement>(null);
  const cityRef = useRef(city);
  cityRef.current = city;
  const introDone = useRef(false);

  const scene = useCanvasLoop(canvas, (c) => {
    const s = new FeederScene(c);
    return {
      onTheme: () => { s.pal = readPalette(); },
      inner: s,
      resize: (w: number) => s.resize(w),
      render: (step: number, dt: number) => {
        const cz = at(cityRef.current?.weather.cos_zenith, step);
        s.render(step, dt, 1 - clamp(cz * 3.2, 0, 1));
      },
    };
  }, []);

  useEffect(() => {
    const holder = scene.current as unknown as { inner: FeederScene } | null;
    const s = holder?.inner;
    if (!s) return;
    s.setData(feeder ?? null, variant === "baseline" ? "gridsetu" : variant);
    if (feeder && !introDone.current) {
      introDone.current = true;
      if (prefersReducedMotion()) s.intro = 1;
      else gsap.fromTo(s, { intro: 0 }, { intro: 1, duration: 1.6, ease: "power2.out", delay: 0.15 });
    }
  }, [feeder, variant, scene]);

  return (
    <div className="relative overflow-hidden rounded-lg border bg-panel">
      <canvas ref={canvas} className="block w-full" role="img"
        aria-label="Pilot feeder: 420 households under the baseline and under GridSetu" />
      {!feeder && <Skeleton className="absolute inset-0 rounded-none" />}
    </div>
  );
}

export function FeederStateLine() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const variant = useUI((s) => s.variant);
  const { data: f } = useFeeder(week);
  const rows = useMemo(() => {
    if (!f) return [];
    const right = variant === "baseline" ? "gridsetu" : variant;
    return (["baseline", right] as const).map((v) => {
      const st = f.state_codes[f.variants[v].state[step]] ?? "normal";
      return { v, st };
    });
  }, [f, step, variant]);
  if (!f) return <Skeleton className="h-12" />;
  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map(({ v, st }) => (
        <div key={v} className="flex items-start gap-2 text-[12.5px] leading-snug">
          <Badge tone={isDark(st) ? (st.includes("island") ? "teal" : "danger") : st === "normal" ? "neutral" : "amber"}>
            {v === "baseline" ? "Baseline" : "GridSetu"}
          </Badge>
          <span className="text-muted-foreground">{STATE_LABEL[st] ?? st}</span>
        </div>
      ))}
    </div>
  );
}
