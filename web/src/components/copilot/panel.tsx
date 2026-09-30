import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { IS_DEMO } from "@/lib/api";
import { providerLabel, useCopilot, type ChatMsg, type CopilotStatus } from "@/lib/copilot";
import { useCity } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { fmtStep } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Markdown } from "./markdown";

const SUGGESTIONS = [
  "What is happening right now?",
  "Why is the price so high at Thu 19:00?",
  "What happened this week?",
  "What if the battery were 400 kWh?",
  "Draft a note for the DISCOM about Thursday evening",
];

export function CopilotButton() {
  const open = useCopilot((s) => s.open);
  return (
    <Tooltip content="Ask the copilot (Ctrl K or /)">
      <Button variant={open ? "secondary" : "outline"} size="sm" onClick={() => useCopilot.getState().toggle()}
        aria-expanded={open} aria-controls="copilot-panel">
        <Icon name="sparkles" className="text-primary" />Copilot
      </Button>
    </Tooltip>
  );
}

function useStatus() {
  return useQuery({
    queryKey: ["copilot-status"], enabled: !IS_DEMO, staleTime: 60_000,
    queryFn: async (): Promise<CopilotStatus> => (await fetch("/api/v1/copilot/status")).json(),
  });
}

/** Docked chat panel. On wide screens it takes a column beside the page; on narrow
 *  screens it slides over it. Opens and closes in 140 ms. */
export function CopilotPanel() {
  const open = useCopilot((s) => s.open);
  const messages = useCopilot((s) => s.messages);
  const busy = useCopilot((s) => s.busy);
  const { send, stop, clear, toggle } = useCopilot.getState();
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const { data: status } = useStatus();

  // Ctrl/Cmd+K or "/" toggles; Escape closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest("input, textarea, [contenteditable]");
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault(); toggle(true); requestAnimationFrame(() => input.current?.focus());
      } else if (e.key === "Escape" && useCopilot.getState().open) toggle(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
  useEffect(() => { if (open) requestAnimationFrame(() => input.current?.focus()); }, [open]);

  // follow the stream unless the reader scrolled up
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const submit = (text = draft) => {
    if (!text.trim() || busy) return;
    stick.current = true;
    setDraft("");
    void send(text);
  };

  return (
    <aside id="copilot-panel" aria-label="Operator copilot" aria-hidden={!open}
      className={cn(
        "fixed inset-y-0 right-0 z-40 flex w-[min(100vw,420px)] flex-col border-l bg-panel shadow-2xl",
        "pt-[env(safe-area-inset-top,0px)] transition-transform duration-150 ease-[var(--ease-snap)] xl:shadow-none",
        open ? "translate-x-0" : "pointer-events-none translate-x-full")}>
      <header className="flex items-center gap-2 border-b px-4 py-3">
        <Icon name="sparkles" className="size-[18px] text-primary" />
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[22px] leading-none">Copilot</h2>
          <p className="mt-1 truncate text-[12px] text-muted-foreground">
            {IS_DEMO ? "Needs the local API" : status ? (status.provider === "offline" ? "Offline assistant, no model configured"
              : providerLabel(status.provider, status.model, status.openai_compatible)) : "Connecting"}
          </p>
        </div>
        {messages.length > 0 && (
          <Tooltip content="Clear the conversation">
            <Button variant="ghost" size="icon-sm" onClick={clear} aria-label="Clear conversation"><Icon name="trash-2" /></Button>
          </Tooltip>
        )}
        <Button variant="ghost" size="icon-sm" onClick={() => toggle(false)} aria-label="Close copilot"><Icon name="x" /></Button>
      </header>

      <div ref={scroller} data-lenis-prevent onScroll={(e) => {
        const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }} className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4" aria-live="polite">
        {messages.length === 0 ? <Welcome onPick={submit} provider={status?.provider} /> :
          messages.map((m) => <Message key={m.id} m={m} />)}
      </div>

      <div className="border-t p-3">
        <ContextLine />
        <div className="relative mt-2">
          <textarea ref={input} value={draft} rows={2} maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder="Ask about the grid, a time, a household, or a what-if"
            aria-label="Message the copilot"
            className="block max-h-40 min-h-[64px] w-full resize-none rounded-lg border bg-background/60 py-2.5 pl-3 pr-12 text-[13.5px] leading-snug outline-none transition-[border-color] duration-100 placeholder:text-faint focus:border-primary" />
          {busy ? (
            <Button size="icon-sm" variant="secondary" className="absolute bottom-2 right-2" onClick={stop} aria-label="Stop"><Icon name="square" /></Button>
          ) : (
            <Button size="icon-sm" className="absolute bottom-2 right-2" disabled={!draft.trim()} onClick={() => submit()} aria-label="Send">
              <Icon name="corner-down-left" />
            </Button>
          )}
        </div>
      </div>
    </aside>
  );
}

function ContextLine() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const { data: city } = useCity(week);
  return (
    <p className="truncate text-[12px] text-muted-foreground">
      Looking at <span className="num text-foreground">{city ? fmtStep(city.t0, city.dt_min, step) : "…"}</span>,{" "}
      {week === "stress" ? "stress week" : "normal week"}
    </p>
  );
}

function Welcome({ onPick, provider }: { onPick: (t: string) => void; provider?: string }) {
  return (
    <div className="space-y-4">
      <p className="text-[13.5px] leading-relaxed text-muted-foreground">
        Ask about what the grid is doing at the playhead, why a price moved, how a household was treated, or test a
        change. Answers come from the simulation, and the dashboard follows along.
      </p>
      {provider === "offline" && (
        <p className="rounded-md border border-amber-fill/30 bg-amber-fill/10 px-3 py-2 text-[12.5px] leading-snug">
          No language model is configured, so the copilot understands a fixed set of questions like the ones below.
          Set <code className="num">ANTHROPIC_API_KEY</code> or run Ollama for free-form questions.
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" onClick={() => onPick(s)}
            className="group flex items-center justify-between gap-2 rounded-md border bg-background/40 px-3 py-2 text-left text-[13px] transition-colors duration-100 hover:border-primary/50 hover:bg-raised/50">
            {s}<Icon name="arrow-right" className="text-faint transition-transform duration-100 group-hover:translate-x-0.5 group-hover:text-primary" />
          </button>
        ))}
      </div>
    </div>
  );
}

function Message({ m }: { m: ChatMsg }) {
  const setRun = useUI((s) => s.setRun);
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-raised px-3 py-2 text-[13.5px]">{m.content}</div>
      </div>
    );
  }
  return (
    <div className="animate-in space-y-2">
      {m.tools.length > 0 && (
        <ul className="space-y-1">
          {m.tools.map((t) => (
            <li key={t.id} className="flex items-start gap-2 text-[12.5px] text-muted-foreground">
              <Icon name={t.status === "running" ? "loader-circle" : t.status === "done" ? "check" : "triangle-alert"}
                className={cn("mt-0.5 size-3.5", t.status === "running" && "animate-spin text-amber", t.status === "done" && "text-primary", t.status === "error" && "text-danger")} />
              <span className="min-w-0">
                {t.label}
                {t.status === "running" && t.progress && <span className="block truncate text-faint">{t.progress}</span>}
                {t.error && <span className="block text-danger">{t.error}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {m.content ? <Markdown text={m.content} /> : m.streaming && m.tools.every((t) => t.status !== "running") && (
        <div className="flex gap-1 py-1" aria-label="Thinking">
          {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-pulse rounded-full bg-faint" style={{ animationDelay: `${i * 150}ms` }} />)}
        </div>
      )}
      {m.offers.map((o) => (
        <Button key={o.run_id} size="sm" variant="outline" onClick={() => setRun(o.run_id)}>
          <Icon name="refresh-cw" />Show “{o.label.replace(/^Copilot: /, "")}” everywhere
        </Button>
      ))}
      {m.error && <p className="rounded-md bg-danger/10 px-3 py-2 text-[12.5px] text-danger">{m.error}</p>}
      {m.provider && !m.streaming && <Badge tone="outline" className="text-[10.5px]">{m.provider}</Badge>}
    </div>
  );
}
