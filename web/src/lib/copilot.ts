import { create } from "zustand";
import { navigate } from "wouter/use-browser-location";
import { IS_DEMO } from "./api";
import { queryClient } from "./queries";
import { useUI } from "./store";

export interface ToolCall {
  id: string; name: string; label: string; status: "running" | "done" | "error"; progress?: string; error?: string;
}
export interface ChatMsg {
  id: string; role: "user" | "assistant"; content: string; tools: ToolCall[];
  offers: { run_id: string; label: string }[]; error?: string; provider?: string; streaming?: boolean;
}
export interface CopilotStatus {
  provider: string; model: string; anthropic_key: boolean; ollama: boolean; openai_compatible?: string | null;
}

const SOURCE_NAME: Record<string, string> = {
  GROQ_API_KEY: "Groq", GEMINI_API_KEY: "Gemini", OPENROUTER_API_KEY: "OpenRouter", OPENAI_API_KEY: "OpenAI",
};
/** Human label for the model behind the copilot. */
export function providerLabel(provider?: string, model?: string, source?: string | null): string {
  if (provider === "claude") return `Claude · ${model}`;
  if (provider === "ollama") return `Ollama · ${model}`;
  if (provider === "openai") return `${(source && SOURCE_NAME[source]) || "OpenAI-compatible"} · ${model}`;
  return "Offline assistant";
}

type UiAction =
  | { type: "seek"; week: "stress" | "representative"; step: number }
  | { type: "week"; week: "stress" | "representative" }
  | { type: "navigate"; path: string }
  | { type: "offer_run"; run_id: string; label: string };

interface CopilotState {
  open: boolean;
  messages: ChatMsg[];
  busy: boolean;
  controller: AbortController | null;
  toggle: (v?: boolean) => void;
  send: (text: string) => Promise<void>;
  stop: () => void;
  clear: () => void;
}

const uid = () => Math.random().toString(36).slice(2, 10);

/** Actions the copilot asks for are applied through the same store actions the UI uses,
 *  so the one-way data flow holds: server event -> store action -> components. */
function applyUi(a: UiAction) {
  const ui = useUI.getState();
  if (a.type === "week" && ui.week !== a.week) ui.setWeek(a.week);
  if (a.type === "seek") {
    if (ui.week !== a.week) ui.setWeek(a.week);
    ui.setPlaying(false);
    ui.seek(a.step);
  }
  if (a.type === "navigate") navigate(a.path);
  if (a.type === "offer_run") queryClient.invalidateQueries({ queryKey: ["runs"] });
}

export const useCopilot = create<CopilotState>((set, get) => ({
  open: false,
  messages: [],
  busy: false,
  controller: null,
  toggle: (v) => set({ open: v ?? !get().open }),
  clear: () => { get().controller?.abort(); set({ messages: [], busy: false, controller: null }); },
  stop: () => { get().controller?.abort(); },
  send: async (text: string) => {
    const q = text.trim();
    if (!q || get().busy) return;
    const user: ChatMsg = { id: uid(), role: "user", content: q, tools: [], offers: [] };
    const bot: ChatMsg = { id: uid(), role: "assistant", content: "", tools: [], offers: [], streaming: true };
    const history = [...get().messages, user].filter((m) => m.content).slice(-20)
      .map((m) => ({ role: m.role, content: m.content }));
    const controller = new AbortController();
    set({ messages: [...get().messages, user, bot], busy: true, controller });
    const patch = (fn: (m: ChatMsg) => ChatMsg) =>
      set({ messages: get().messages.map((m) => (m.id === bot.id ? fn(m) : m)) });

    if (IS_DEMO) {
      patch((m) => ({ ...m, streaming: false, error: "The copilot needs the local GridSetu API. Run `gridsetu serve` and open http://127.0.0.1:8000." }));
      set({ busy: false, controller: null });
      return;
    }
    const ui = useUI.getState();
    const runs = queryClient.getQueryData<{ reference: string }>(["runs"]);
    // text deltas are buffered and flushed once per frame, so long answers never re-render per token
    let pending = "";
    let raf = 0;
    const flush = () => { raf = 0; if (pending) { const p = pending; pending = ""; patch((m) => ({ ...m, content: m.content + p })); } };
    try {
      const res = await fetch("/api/v1/copilot/chat", {
        method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history, context: {
          run_id: ui.runId ?? runs?.reference ?? null, week: ui.week, step: Math.floor(ui.step),
          page: window.location.pathname } }),
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `The copilot returned ${res.status}`);
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
          if (!chunk.startsWith("data: ")) continue;
          const ev = JSON.parse(chunk.slice(6));
          switch (ev.type) {
            case "meta": patch((m) => ({ ...m, provider: providerLabel(ev.provider, ev.model) })); break;
            case "text": pending += ev.delta; if (!raf) raf = requestAnimationFrame(flush); break;
            case "tool_start": flush(); patch((m) => ({ ...m, tools: [...m.tools, { id: ev.id, name: ev.name, label: ev.label, status: "running" }] })); break;
            case "tool_progress": patch((m) => ({ ...m, tools: m.tools.map((t) => (t.id === ev.id ? { ...t, progress: ev.message } : t)) })); break;
            case "tool_end": patch((m) => ({ ...m, tools: m.tools.map((t) => (t.id === ev.id ? { ...t, status: ev.ok ? "done" : "error", error: ev.error } : t)) })); break;
            case "ui":
              applyUi(ev.action as UiAction);
              if (ev.action.type === "offer_run") patch((m) => ({ ...m, offers: [...m.offers, { run_id: ev.action.run_id, label: ev.action.label }] }));
              break;
            case "error": flush(); patch((m) => ({ ...m, error: ev.message })); break;
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") patch((m) => ({ ...m, error: (e as Error).message }));
      else patch((m) => ({ ...m, error: m.content ? undefined : "Stopped." }));
    } finally {
      if (raf) cancelAnimationFrame(raf);
      flush();
      patch((m) => ({ ...m, streaming: false, content: m.content.trim() }));
      set({ busy: false, controller: null });
    }
  },
}));
