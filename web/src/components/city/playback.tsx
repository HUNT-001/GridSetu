import { useEffect, useMemo, useRef } from "react";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { useCity } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { clamp } from "@/lib/utils";

const SPEEDS = [
  { value: "2", label: "2×", title: "2 steps (30 min) per second" },
  { value: "6", label: "6×", title: "6 steps (1.5 h) per second" },
  { value: "24", label: "24×", title: "A day in 4 seconds" },
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Week scrubber. The thumb and fill follow the clock through direct style writes, so
 *  dragging and playback stay at frame rate without re-rendering React. */
export function PlaybackBar() {
  const playing = useUI((s) => s.playing);
  const speed = useUI((s) => s.speed);
  const n = useUI((s) => s.nSteps);
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { togglePlay, seek, setSpeed, setPlaying } = useUI.getState();
  const { data: city } = useCity(week);
  const track = useRef<HTMLDivElement>(null);
  const fill = useRef<HTMLDivElement>(null);
  const thumb = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const place = (step: number) => {
      const f = (step / Math.max(n - 1, 1)) * 100;
      if (fill.current) fill.current.style.width = `${f}%`;
      if (thumb.current) thumb.current.style.left = `${f}%`;
      track.current?.setAttribute("aria-valuenow", String(Math.floor(step)));
    };
    place(useUI.getState().step);
    return useUI.subscribe((s) => place(s.step));
  }, [n]);

  // Space toggles playback, arrows step 15 min (shift: 1 h), unless typing in a field
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, [role=slider], [contenteditable]")) return;
      if (e.code === "Space") { e.preventDefault(); togglePlay(); }
      if (e.code === "ArrowRight" || e.code === "ArrowLeft") {
        e.preventDefault();
        const d = (e.shiftKey ? 4 : 1) * (e.code === "ArrowRight" ? 1 : -1);
        seek(Math.round(useUI.getState().step) + d);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, seek]);

  const fromPointer = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    return clamp((clientX - r.left) / r.width, 0, 1) * (n - 1);
  };

  const markers = useMemo(() => (city?.scenarios[scen].events ?? []).filter((e) => e.kind !== "restore"), [city, scen]);
  const days = Math.round(n / 96);
  const startDow = city ? (new Date(`${city.t0}Z`).getUTCDay() + 6) % 7 : 0;

  return (
    <div className="flex items-center gap-3">
      <Button size="icon" variant="default" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
        <Icon name={playing ? "pause" : "play"} />
      </Button>
      <Tooltip content="Back to the start of the week">
        <Button size="icon-sm" variant="ghost" onClick={() => seek(0)} aria-label="Back to start">
          <Icon name="skip-back" />
        </Button>
      </Tooltip>
      <div className="relative flex-1 py-3">
        <div ref={track} role="slider" tabIndex={0} aria-label="Simulation time" aria-valuemin={0}
          aria-valuemax={n - 1}
          className="relative h-1.5 cursor-pointer rounded-full bg-raised"
          onPointerDown={(e) => {
            dragging.current = true;
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
            setPlaying(false);
            seek(fromPointer(e.clientX));
          }}
          onPointerMove={(e) => { if (dragging.current) seek(fromPointer(e.clientX)); }}
          onPointerUp={() => { dragging.current = false; }}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight") { e.preventDefault(); seek(Math.round(useUI.getState().step) + (e.shiftKey ? 4 : 1)); }
            if (e.key === "ArrowLeft") { e.preventDefault(); seek(Math.round(useUI.getState().step) - (e.shiftKey ? 4 : 1)); }
          }}>
          <div ref={fill} className="absolute inset-y-0 left-0 rounded-full bg-primary/70" />
          {markers.map((m) => (
            <span key={`${m.kind}-${m.step}`} title={m.label}
              className={`absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-panel ${m.kind === "outage" ? "bg-danger" : "bg-amber-fill"}`}
              style={{ left: `${(m.step / (n - 1)) * 100}%` }} />
          ))}
          <div ref={thumb}
            className="pointer-events-none absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-primary bg-panel shadow" />
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-6 hidden text-[11px] text-faint sm:flex">
          {Array.from({ length: days }, (_, d) => (
            <span key={d} className="flex-1 pl-0.5">{DAYS[(startDow + d) % 7]}</span>
          ))}
        </div>
      </div>
      <Segmented label="Playback speed" size="sm" value={String(speed)} onChange={(v) => setSpeed(Number(v))} options={SPEEDS} />
    </div>
  );
}
