import { useEffect } from "react";
import { Link, useLocation } from "wouter";
import { DropdownMenu } from "radix-ui";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip } from "@/components/ui/tooltip";
import { IS_DEMO } from "@/lib/api";
import { useActiveRun, useRunProgress, useRuns } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { IconName } from "@/icons/sprite.gen";
import type { Week } from "@/lib/types";
import { cn } from "@/lib/utils";

export const NAV: { href: string; label: string; icon: IconName; title: string; blurb: string }[] = [
  { href: "/", label: "Control room", icon: "layout-dashboard", title: "Control room",
    blurb: "The whole city and the pilot feeder, minute by minute." },
  { href: "/city", label: "City and market", icon: "building-2", title: "City and market",
    blurb: "Generation, the day-ahead market, transmission and who gets shed." },
  { href: "/feeder", label: "Pilot feeder", icon: "zap", title: "Pilot feeder F07",
    blurb: "Battery, tiers, curtailment requests and the Reliability Reserve." },
  { href: "/households", label: "Households", icon: "users", title: "Households and fairness",
    blurb: "Every home on the feeder and every curtailment it received." },
  { href: "/wams", label: "Protection", icon: "activity", title: "Protection and WAMS",
    blurb: "Sub-second frequency after a generator trip and after islanding." },
  { href: "/architecture", label: "Architecture", icon: "layers", title: "Grid architecture",
    blurb: "The five layers, what runs in each, and how they talk." },
  { href: "/lab", label: "Scenario lab", icon: "flask-conical", title: "Scenario lab",
    blurb: "Change the battery, the transformer or the comms and rerun." },
];

export function Sidebar() {
  const [loc] = useLocation();
  const collapsed = useUI((s) => s.sidebarCollapsed);
  return (
    <aside className={cn(
      "sticky top-0 z-30 hidden h-dvh shrink-0 flex-col border-r bg-panel md:flex",
      "transition-[width] duration-150 ease-[var(--ease-snap)]", collapsed ? "w-[60px]" : "w-[220px]")}>
      <div className="flex h-14 items-center gap-2.5 px-4">
        <svg viewBox="0 0 24 24" className="size-7 shrink-0" aria-hidden>
          <rect width="24" height="24" rx="6" fill="var(--raised)" />
          <path d="M5 16h14" stroke="var(--primary)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M7 16c1.5-5 3-7.5 5-7.5S15.5 11 17 16" fill="none" stroke="var(--primary)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M12.6 4.5 10.4 8.2h2.4l-1 3.1" fill="none" stroke="var(--amber-fill)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {!collapsed && <span className="font-display text-[23px] leading-none">GridSetu</span>}
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-2 pt-2" aria-label="Main">
        {NAV.map((n) => {
          const active = n.href === "/" ? loc === "/" : loc.startsWith(n.href);
          const link = (
            <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
              className={cn(
                "group flex h-9 items-center gap-3 rounded-md px-2.5 text-[13.5px] font-medium",
                "transition-[background-color,color] duration-100",
                active ? "bg-raised text-foreground" : "text-muted-foreground hover:bg-raised/60 hover:text-foreground")}>
              <Icon name={n.icon} className={cn("size-[18px]", active && "text-primary")} />
              {!collapsed && <span className="truncate">{n.label}</span>}
            </Link>
          );
          return collapsed ? <Tooltip key={n.href} side="right" content={n.label}>{link}</Tooltip> : link;
        })}
      </nav>
      <div className="border-t p-2">
        <Button variant="ghost" size="sm" className="w-full justify-start" onClick={useUI.getState().toggleSidebar}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <Icon name="panel-left" />
          {!collapsed && "Collapse"}
        </Button>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const [loc] = useLocation();
  return (
    <nav className="sticky bottom-0 z-30 flex justify-around border-t bg-panel/95 pt-1.5 pb-[calc(0.375rem+env(safe-area-inset-bottom,0px))] backdrop-blur md:hidden" aria-label="Main">
      {NAV.map((n) => {
        const active = n.href === "/" ? loc === "/" : loc.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} aria-label={n.label}
            className={cn("rounded-md p-2", active ? "text-primary" : "text-muted-foreground")}>
            <Icon name={n.icon} className="size-5" />
          </Link>
        );
      })}
    </nav>
  );
}

export function Topbar() {
  const [loc] = useLocation();
  const page = NAV.find((n) => (n.href === "/" ? loc === "/" : loc.startsWith(n.href))) ?? NAV[0];
  const week = useUI((s) => s.week);
  const theme = useUI((s) => s.theme);
  const { setWeek, toggleTheme } = useUI.getState();
  useEffect(() => { document.title = `${page.title}, GridSetu`; }, [page.title]);
  return (
    <header className="sticky top-[env(safe-area-inset-top,0px)] z-20 border-b bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:px-6">
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-[30px] leading-[1.05]">{page.title}</h1>
          <p className="truncate text-[12.5px] text-muted-foreground">{page.blurb}</p>
        </div>
        <Segmented<Week> label="Week" value={week} onChange={setWeek} options={[
          { value: "stress", label: "Stress week", title: "Forced coal-unit outage and two overcast days" },
          { value: "representative", label: "Normal week", title: "No outage" },
        ]} />
        <RunPicker />
        <Tooltip content={theme === "dark" ? "Switch to light" : "Switch to dark"}>
          <Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label="Toggle colour theme">
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </Button>
        </Tooltip>
      </div>
      <RunProgressBar />
    </header>
  );
}

function RunPicker() {
  const { data } = useRuns();
  const { id, run } = useActiveRun();
  const setRun = useUI((s) => s.setRun);
  const runs = data?.runs ?? [];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="outline" size="sm" className="max-w-56" aria-label="Choose scenario run">
          <span className={cn("size-2 rounded-full", run?.status === "ready" ? "bg-primary" : run?.status === "failed" ? "bg-danger" : "animate-pulse bg-amber-fill")} />
          <span className="truncate">{run?.label ?? "Connecting"}</span>
          <Icon name="chevron-down" className="text-muted-foreground" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6}
          className="z-50 min-w-64 rounded-lg border bg-panel p-1 shadow-xl data-[state=open]:animate-in">
          <DropdownMenu.Label className="px-2 py-1.5 text-[12px] text-muted-foreground">
            {IS_DEMO ? "Bundled snapshot" : "Scenario runs"}
          </DropdownMenu.Label>
          {runs.map((r) => (
            <DropdownMenu.Item key={r.id} disabled={r.status !== "ready"}
              onSelect={() => setRun(r.id === data?.reference ? null : r.id)}
              className="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-[13px] outline-none transition-colors duration-100 data-[highlighted]:bg-raised data-[disabled]:opacity-50">
              <Icon name={r.id === id ? "check" : "circle-dot"} className={cn(r.id === id ? "text-primary" : "text-faint")} />
              <span className="flex-1 truncate">{r.label}</span>
              <span className="num text-[11.5px] text-faint">
                {r.status === "ready" ? `${r.seeds} seed${r.seeds > 1 ? "s" : ""}` : `${Math.round(r.progress * 100)}%`}
              </span>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function RunProgressBar() {
  const { data } = useRuns();
  const pending = data?.runs.find((r) => r.status === "running" || r.status === "queued");
  const live = useRunProgress(pending?.id ?? null);
  const rec = live ?? pending;
  if (!rec || rec.status === "ready" || rec.status === "failed") return null;
  return (
    <div className="relative h-0.5 bg-raised" role="progressbar" aria-valuenow={Math.round(rec.progress * 100)}
      aria-valuemin={0} aria-valuemax={100} aria-label={`${rec.label}: ${rec.message}`}>
      <div className="h-full bg-primary transition-[width] duration-150" style={{ width: `${rec.progress * 100}%` }} />
    </div>
  );
}
