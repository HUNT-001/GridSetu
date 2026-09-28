import { create } from "zustand";
import type { CityScenario, Variant, Week } from "./types";

/** UI state only. Server data lives in TanStack Query; this store never holds payloads.
 *  Data flows one way: store -> selectors -> components -> actions -> store. */
interface UIState {
  runId: string | null;
  week: Week;
  variant: Variant;
  cityScenario: CityScenario;
  compare: boolean;
  playing: boolean;
  speed: number;           // simulation steps per second
  step: number;            // fractional playhead
  nSteps: number;
  theme: "dark" | "light";
  sidebarCollapsed: boolean;
  setRun: (id: string | null) => void;
  setWeek: (w: Week) => void;
  setVariant: (v: Variant) => void;
  setCityScenario: (s: CityScenario) => void;
  setCompare: (c: boolean) => void;
  setPlaying: (p: boolean) => void;
  togglePlay: () => void;
  seek: (step: number) => void;
  setSpeed: (s: number) => void;
  setNSteps: (n: number) => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
}

/** Theme: the viewer's saved choice, else a host-set data-theme, else the OS setting. */
export const initialTheme = (): "dark" | "light" => {
  try { const t = localStorage.getItem("gs-theme"); if (t === "light" || t === "dark") return t; } catch { /* blocked */ }
  const host = document.documentElement.getAttribute("data-theme");
  if (host === "light" || host === "dark") return host;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
};

// The stress week's most telling moment: Thursday 18:00, the instant G1B trips.
export const HERO_STEP = 3 * 96 + 72;

export const useUI = create<UIState>((set, get) => ({
  runId: null,
  week: "stress",
  variant: "gridsetu",
  cityScenario: "baseline",
  compare: true,
  playing: false,
  speed: 6,
  step: HERO_STEP,
  nSteps: 672,
  theme: initialTheme(),
  sidebarCollapsed: false,
  setRun: (runId) => set({ runId }),
  setWeek: (week) => set({ week, step: week === "stress" ? HERO_STEP : 69 + 96 }),
  setVariant: (variant) => set({ variant }),
  setCityScenario: (cityScenario) => set({ cityScenario }),
  setCompare: (compare) => set({ compare }),
  setPlaying: (playing) => set({ playing }),
  togglePlay: () => set({ playing: !get().playing }),
  seek: (step) => set({ step: Math.max(0, Math.min(get().nSteps - 1, step)) }),
  setSpeed: (speed) => set({ speed }),
  setNSteps: (nSteps) => set({ nSteps }),
  toggleTheme: () => {
    const theme = get().theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("gs-theme", theme); } catch { /* private mode */ }
    set({ theme });
  },
  toggleSidebar: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
}));

/** Integer step: components re-render only when the playhead crosses a 15-min boundary. */
export const useStepInt = () => useUI((s) => Math.floor(s.step));

/** Single rAF clock for the whole app. Canvas and chart cursors read the fractional
 *  step transiently (subscribe), so React never re-renders at frame rate. */
let raf = 0;
let last = 0;
export function startClock() {
  if (raf) return;
  const tick = (now: number) => {
    const s = useUI.getState();
    if (s.playing) {
      const dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
      let next = s.step + dt * s.speed;
      if (next >= s.nSteps - 1) next = 0;
      useUI.setState({ step: next });
    }
    last = now;
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
}
