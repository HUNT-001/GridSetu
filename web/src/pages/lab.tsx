import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon } from "@/components/icon";
import { api, IS_DEMO } from "@/lib/api";
import { queryClient, useRunProgress, useRuns } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { change, f0, f1 } from "@/lib/format";
import type { LabKnobs, Summary } from "@/lib/types";
import { cn } from "@/lib/utils";

type NumKey = "battery_kwh" | "battery_kw" | "capacity_kw" | "tier1_island_hours" | "control_loss" | "industrial_dr_mw";
const SLIDERS: { key: NumKey; label: string; min: number; max: number; step: number; fmt: (v: number) => string; help: string }[] = [
  { key: "battery_kwh", label: "Battery energy", min: 50, max: 600, step: 25, fmt: (v) => `${f0(v)} kWh`, help: "Community battery size" },
  { key: "battery_kw", label: "Battery power", min: 25, max: 250, step: 5, fmt: (v) => `${f0(v)} kW`, help: "Inverter rating" },
  { key: "capacity_kw", label: "Transformer rating", min: 250, max: 400, step: 10, fmt: (v) => `${f0(v)} kW`, help: "Where overload trips start" },
  { key: "tier1_island_hours", label: "Critical-load reserve", min: 0, max: 4, step: 0.5, fmt: (v) => `${f1(v)} h`, help: "Battery held back for islanding" },
  { key: "control_loss", label: "Control-message loss", min: 0, max: 0.8, step: 0.05, fmt: (v) => `${f0(v * 100)}%`, help: "Per attempt on the 2G/4G slice" },
  { key: "industrial_dr_mw", label: "Industrial demand response", min: 0, max: 40, step: 5, fmt: (v) => `${f0(v)} MW`, help: "City-level interruptible contracts" },
];

export default function LabPage() {
  const defaults = useQuery({ queryKey: ["lab-defaults"], queryFn: api.defaults });
  const [knobs, setKnobs] = useState<LabKnobs | null>(null);
  const [label, setLabel] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const setRun = useUI((s) => s.setRun);
  const { data: runs } = useRuns();
  const progress = useRunProgress(jobId);
  useEffect(() => { if (defaults.data && !knobs) setKnobs(defaults.data); }, [defaults.data, knobs]);

  const start = useMutation({
    mutationFn: () => api.startRun(knobs!, label.trim() || describe(knobs!, defaults.data!)),
    onSuccess: (r) => { setJobId(r.id); queryClient.invalidateQueries({ queryKey: ["runs"] }); },
  });
  const job = progress ?? runs?.runs.find((r) => r.id === jobId);

  if (!knobs || !defaults.data) return <Skeleton className="h-[520px]" />;
  const d = defaults.data;
  const changed = (Object.keys(d) as (keyof LabKnobs)[]).filter((k) => d[k] !== knobs[k]);

  return (
    <div className="grid gap-4 xl:grid-cols-[440px_minmax(0,1fr)]">
      <Card className="self-start">
        <CardHeader>
          <div>
            <CardTitle>Change the scenario</CardTitle>
            <CardDescription>One seed, both weeks, about a minute on a laptop. Results open in every page when ready.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {SLIDERS.map((s) => (
            <div key={s.key}>
              <div className="mb-1.5 flex items-baseline justify-between text-[13px]">
                <label className="font-medium">{s.label}</label>
                <span className={cn("num", knobs[s.key] !== d[s.key] && "text-primary")}>{s.fmt(knobs[s.key])}</span>
              </div>
              <Slider label={s.label} value={knobs[s.key]} min={s.min} max={s.max} step={s.step}
                onChange={(v) => setKnobs({ ...knobs, [s.key]: v })} />
              <p className="mt-1 text-[12px] text-faint">{s.help}, default {s.fmt(d[s.key])}</p>
            </div>
          ))}
          <div className="space-y-3 border-t pt-4">
            {([["forced_outage", "Forced coal-unit outage in the stress week"],
               ["irrigation_shift", "Solar-hour irrigation in the coordinated city"]] as const).map(([k, l]) => (
              <label key={k} className="flex items-center justify-between gap-3 text-[13px]">
                {l}
                <Switch label={l} checked={knobs[k]} onChange={(v) => setKnobs({ ...knobs, [k]: v })} />
              </label>
            ))}
          </div>
          <div className="space-y-2 border-t pt-4">
            <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60}
              placeholder={describe(knobs, d)}
              className="h-9 w-full rounded-md border bg-background/50 px-3 text-[13px] outline-none transition-[border-color] duration-100 placeholder:text-faint focus:border-primary"
              aria-label="Run name" />
            <div className="flex gap-2">
              <Button className="flex-1" disabled={IS_DEMO || start.isPending || job?.status === "running" || job?.status === "queued"}
                onClick={() => start.mutate()}>
                <Icon name="play" />Run scenario
              </Button>
              <Button variant="ghost" disabled={changed.length === 0} onClick={() => setKnobs(d)}>Reset</Button>
            </div>
            {IS_DEMO && <p className="text-[12px] text-amber">This shared copy has no simulator behind it. Run it locally with the API to try scenarios.</p>}
            {start.isError && <p className="text-[12px] text-danger">{(start.error as Error).message}</p>}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {job && (
          <Card>
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center gap-3">
                <Icon name={job.status === "ready" ? "circle-check" : job.status === "failed" ? "triangle-alert" : "loader-circle"}
                  className={cn("size-5", job.status === "ready" ? "text-primary" : job.status === "failed" ? "text-danger" : "animate-spin text-amber")} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px] font-medium">{job.label}</div>
                  <div className="truncate text-[12.5px] text-muted-foreground">{job.status === "failed" ? job.error : job.message}</div>
                </div>
                {job.status === "ready" && <Button size="sm" onClick={() => setRun(job.id)}>Show everywhere</Button>}
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-raised">
                <div className="h-full rounded-full bg-primary transition-[width] duration-150" style={{ width: `${job.progress * 100}%` }} />
              </div>
            </CardContent>
          </Card>
        )}
        <Compare jobId={job?.status === "ready" ? job.id : null} reference={runs?.reference ?? null} />
      </div>
    </div>
  );
}

function describe(k: LabKnobs, d: LabKnobs): string {
  const parts: string[] = [];
  if (k.battery_kwh !== d.battery_kwh || k.battery_kw !== d.battery_kw) parts.push(`${k.battery_kwh} kWh / ${k.battery_kw} kW`);
  if (k.capacity_kw !== d.capacity_kw) parts.push(`${k.capacity_kw} kW DT`);
  if (k.control_loss !== d.control_loss) parts.push(`${Math.round(k.control_loss * 100)}% loss`);
  if (k.tier1_island_hours !== d.tier1_island_hours) parts.push(`${k.tier1_island_hours} h reserve`);
  if (k.forced_outage !== d.forced_outage) parts.push(k.forced_outage ? "outage" : "no outage");
  if (k.irrigation_shift !== d.irrigation_shift) parts.push(k.irrigation_shift ? "solar irrigation" : "legacy irrigation");
  if (k.industrial_dr_mw !== d.industrial_dr_mw) parts.push(`${k.industrial_dr_mw} MW DR`);
  return parts.length ? parts.join(", ") : "Reference settings";
}

const ROWS: [string, string, (v: number) => string][] = [
  ["evening_window_unserved_kwh", "Unserved energy, 17:30 to 19:30 (kWh)", f0],
  ["total_unserved_kwh", "Unserved energy, all hours (kWh)", f0],
  ["critical_outage_hours", "Critical-load outage (h)", f1],
  ["feeder_outage_hours", "Whole feeder dark (h)", f1],
  ["feeder_peak_import_kw", "Peak from the grid (kW)", f0],
  ["overload_trips", "Overload trips", f0],
  ["battery_cycles", "Battery cycles", f1],
];

function Compare({ jobId, reference }: { jobId: string | null; reference: string | null }) {
  const ref = useQuery({ queryKey: ["res", reference, "summary", null], queryFn: () => api.resource<Summary>(reference!, "summary"), enabled: !!reference });
  const lab = useQuery({ queryKey: ["res", jobId, "summary", null], queryFn: () => api.resource<Summary>(jobId!, "summary"), enabled: !!jobId });
  if (!ref.data) return <Skeleton className="h-80" />;
  const R = ref.data.monthly, L = lab.data?.monthly;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>A month on F07, reference versus your scenario</CardTitle>
          <CardDescription>GridSetu figures. The reference averages {ref.data.monthly.baseline.critical_outage_hours.max !== ref.data.monthly.baseline.critical_outage_hours.min ? "several seeds" : "one seed"}; lab runs use one, so small differences can be noise.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-[13px]">
          <thead className="text-left text-[12px] text-muted-foreground">
            <tr className="border-b">
              <th className="py-2 font-medium">Metric</th>
              <th className="py-2 text-right font-medium">Baseline</th>
              <th className="py-2 text-right font-medium">GridSetu, reference</th>
              <th className="py-2 text-right font-medium">GridSetu, your run</th>
              <th className="py-2 text-right font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([k, label, fmt]) => {
              const b = R.baseline[k]?.mean ?? 0, g = R.gridsetu[k]?.mean ?? 0, x = L?.gridsetu[k]?.mean;
              return (
                <tr key={k} className="border-b border-border/60">
                  <td className="py-2">{label}</td>
                  <td className="num text-right text-muted-foreground">{fmt(b)}</td>
                  <td className="num text-right">{fmt(g)}</td>
                  <td className="num text-right">{x === undefined ? "–" : fmt(x)}</td>
                  <td className="num text-right">{x === undefined ? "" : change(g, x)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!L && <p className="mt-3 text-[12.5px] text-muted-foreground">Run a scenario to fill in the last two columns.</p>}
      </CardContent>
    </Card>
  );
}
