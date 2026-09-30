import { create } from "zustand";
import { IS_DEMO } from "./api";
import { queryClient } from "./queries";
import { useUI } from "./store";

export interface Scada { ts: string; state: string; import_kw: number; battery_kw: number; soc_pct: number; critical_on: boolean; baseline_state: string }
export interface Ami { meters: number; reads_received: number; fully_supplied_pct: number; tier3_paused_kw: number }
export interface CityMsg { demand_mw: number; shed_mw: number; import_mw: number; renewables_mw: number }

interface LiveState {
  on: boolean; mqtt: boolean; messages: number; scada: Scada | null; ami: Ami | null; city: CityMsg | null;
  reserve: string | null; error: string | null;
  start: () => void; stop: () => void;
}

let es: EventSource | null = null;

/** Live mode: the server replays the run as telemetry (SCADA, AMI, city state, reserve
 *  publications) and drives the playhead. The local clock stands down while it is on. */
export const useLive = create<LiveState>((set, get) => ({
  on: false, mqtt: false, messages: 0, scada: null, ami: null, city: null, reserve: null, error: null,
  start: () => {
    if (IS_DEMO) { set({ error: "Live replay needs the local API." }); return; }
    es?.close();
    const ui = useUI.getState();
    ui.setPlaying(false);
    const runs = queryClient.getQueryData<{ reference: string }>(["runs"]);
    const run = ui.runId ?? runs?.reference ?? "";
    const qs = new URLSearchParams({ run, week: ui.week, start: String(Math.floor(ui.step)), speed: String(ui.speed) });
    es = new EventSource(`/api/v1/live/stream?${qs}`);
    set({ on: true, error: null, messages: 0 });
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "hello") { set({ mqtt: !!ev.mqtt }); return; }
      if (ev.type !== "tick") return;
      const patch: Partial<LiveState> = { messages: get().messages + ev.messages.length };
      for (const m of ev.messages as { topic: string; payload: never }[]) {
        if (m.topic.endsWith("/scada")) patch.scada = m.payload;
        else if (m.topic.endsWith("/ami")) patch.ami = m.payload;
        else if (m.topic === "city/state") patch.city = m.payload;
        else if (m.topic.endsWith("/reserve")) patch.reserve = `${(m.payload as { stage: string }).stage} reserve published`;
      }
      set(patch);
      useUI.getState().seek(ev.step);
    };
    es.onerror = () => { set({ error: "Live stream interrupted. Press Live again to reconnect." }); get().stop(); };
  },
  stop: () => { es?.close(); es = null; set({ on: false }); },
}));

// restart the stream when the week, run or speed changes; any manual play stops it
useUI.subscribe((s, p) => {
  const live = useLive.getState();
  if (!live.on) return;
  if (s.playing) { live.stop(); return; }
  if (s.week !== p.week || s.runId !== p.runId || s.speed !== p.speed) live.start();
});
