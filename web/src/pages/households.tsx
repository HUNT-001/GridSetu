import { useDeferredValue, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Icon } from "@/components/icon";
import { Kpi } from "@/components/kpi";
import { Sparkline } from "@/components/charts/spark";
import { DataTable, type Column } from "@/components/data-table";
import { useFeeder, useHouseholds } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { f0, f1, f2, fmtStep } from "@/lib/format";
import { decodeB64 } from "@/lib/utils";

interface HhRow { i: number; id: string; node: number; peak: number; energy: number; t3: number; curtailed: number;
  events: number; darkB: number; darkG: number; daily: number[] }
interface LogRow { k: number; step: number; time: string; hh: string; kw: number }

export default function HouseholdsPage() {
  const week = useUI((s) => s.week);
  const { data: h } = useHouseholds(week);
  const [q, setQ] = useState("");
  const query = useDeferredValue(q);        // typing stays instant; filtering follows
  const [open, setOpen] = useState<HhRow | null>(null);

  const rows = useMemo<HhRow[]>(() => {
    if (!h) return [];
    const x = h.households;
    return x.id.map((id, i) => ({ i, id, node: x.node[i], peak: x.peak_kw[i], energy: x.energy_kwh[i],
      t3: x.tier3_kwh[i], curtailed: x.curtailed_h[i], events: x.events[i], darkB: x.dark_h_baseline[i],
      darkG: x.dark_h_gridsetu[i], daily: x.daily_kwh[i] }));
  }, [h]);
  const log = useMemo<LogRow[]>(() => {
    if (!h) return [];
    const L = h.curtailment_log;
    return L.step.map((s, k) => ({ k, step: s, time: fmtStep(h.t0, h.dt_min, s), hh: h.households.id[L.hh[k]], kw: L.kw[k] }));
  }, [h]);

  const hhCols = useMemo<Column<HhRow>[]>(() => [
    { key: "id", header: "Household", width: "110px", value: (r) => r.id, mono: true },
    { key: "node", header: "Section", width: "96px", value: (r) => r.node, align: "right", mono: true },
    { key: "peak", header: "Peak kW", width: "104px", value: (r) => r.peak, align: "right", mono: true, cell: (r) => f2(r.peak) },
    { key: "energy", header: "Energy kWh", width: "124px", value: (r) => r.energy, align: "right", mono: true, cell: (r) => f1(r.energy) },
    { key: "curtailed", header: "Paused h", width: "108px", value: (r) => r.curtailed, align: "right", mono: true, cell: (r) => f2(r.curtailed) },
    { key: "events", header: "Events", width: "92px", value: (r) => r.events, align: "right", mono: true },
    { key: "darkB", header: "Dark h, base", width: "124px", value: (r) => r.darkB, align: "right", mono: true, cell: (r) => f2(r.darkB) },
    { key: "darkG", header: "Dark h, Setu", width: "124px", value: (r) => r.darkG, align: "right", mono: true, cell: (r) => f2(r.darkG) },
    { key: "daily", header: "Daily energy", width: "minmax(100px,1fr)", value: (r) => r.energy,
      cell: (r) => <Sparkline values={r.daily} /> },
  ], []);
  const logCols = useMemo<Column<LogRow>[]>(() => [
    { key: "time", header: "Interval", width: "170px", value: (r) => r.step, cell: (r) => r.time, mono: true },
    { key: "hh", header: "Household", width: "120px", value: (r) => r.hh, mono: true },
    { key: "kw", header: "Paused kW", width: "110px", value: (r) => r.kw, align: "right", mono: true, cell: (r) => f2(r.kw) },
    { key: "why", header: "Reason", width: "1fr", value: () => "Tier-3 appliance paused",
      cell: () => <span className="text-muted-foreground">Tier-3 appliances paused for 15 minutes</span> },
  ], []);

  if (!h) return <Skeleton className="h-[600px]" />;
  const fs = h.fairness;
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="grid grid-cols-2 gap-5 pt-4 md:grid-cols-4">
          <Kpi label="Homes that shared curtailment" format={f0} value={fs.households_ever_curtailed ?? 0} unit={`of ${rows.length}`} />
          <Kpi label="Most hours paused, any home" unit="h" format={f2} value={fs.max_household_hours ?? 0} />
          <Kpi label="Gini of paused hours" format={f2} value={fs.gini_curtailment_hours ?? 0} hint="0 means perfectly even" />
          <Kpi label="Overrides honoured" format={f0} value={fs.refusals ?? 0} hint="Households that said no to a request" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-wrap">
          <div>
            <CardTitle>Every home on F07</CardTitle>
            <CardDescription>The ledger never pauses the same home in two consecutive 15-minute intervals and always asks the least-curtailed homes first.</CardDescription>
          </div>
          <label className="relative block w-full max-w-64">
            <Icon name="search" className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a household or time"
              className="h-8 w-full rounded-md border bg-background/50 pl-8 pr-2 text-[13px] outline-none transition-[border-color] duration-100 placeholder:text-faint focus:border-primary" />
          </label>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="homes">
            <TabsList>
              <TabsTrigger value="homes">Households <span className="num ml-1 text-faint">{rows.length}</span></TabsTrigger>
              <TabsTrigger value="log">Curtailment log <span className="num ml-1 text-faint">{log.length.toLocaleString("en-IN")}</span></TabsTrigger>
            </TabsList>
            <TabsContent value="homes">
              <DataTable label="Households" rows={rows} columns={hhCols} minWidth={1000} search={query} onRowClick={setOpen}
                initialSort={{ key: "curtailed", dir: -1 }} />
            </TabsContent>
            <TabsContent value="log">
              <DataTable label="Curtailment log" rows={log} columns={logCols} search={query}
                initialSort={{ key: "time", dir: 1 }} empty="No curtailment this week. The battery covered every request." />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
      <Enterprises />
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        {open && (
          <DialogContent title={open.id} description={`Section ${open.node} of the feeder, peak ${f2(open.peak)} kW, ${f1(open.energy)} kWh this week.`}
            className="w-[min(94vw,760px)]">
            <HouseholdStrip index={open.i} />
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

function HouseholdStrip({ index }: { index: number }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const strips = useMemo(() => {
    if (!f) return null;
    return (["baseline", "gridsetu"] as const).map((v) => {
      const st = decodeB64(f.variants[v].hh_status_b64);
      const out: number[] = [];
      for (let t = 0; t < f.n; t++) out.push(st[t * f.n_households + index]);
      return { v, out };
    });
  }, [f, index]);
  if (!f || !strips) return <Skeleton className="h-24" />;
  const COL = ["var(--amber-fill)", "var(--primary)", "var(--raised)"];
  return (
    <div className="space-y-3">
      {strips.map(({ v, out }) => (
        <div key={v}>
          <div className="mb-1 text-[12.5px] text-muted-foreground">{v === "baseline" ? "Baseline" : "GridSetu"}</div>
          <svg viewBox={`0 0 ${out.length} 10`} preserveAspectRatio="none" className="h-6 w-full rounded-sm" aria-hidden>
            {out.map((s, t) => <rect key={t} x={t} y={0} width={1.05} height={10} fill={COL[s]} />)}
          </svg>
        </div>
      ))}
      <div className="flex gap-4 text-[12px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-amber-fill" />Supplied</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-primary" />Tier-3 paused</span>
        <span className="inline-flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-raised" />No supply</span>
        <span className="ml-auto">Monday to Sunday</span>
      </div>
    </div>
  );
}

function Enterprises() {
  const week = useUI((s) => s.week);
  const { data: h } = useHouseholds(week);
  if (!h) return null;
  const e = h.enterprises;
  const optIn = e.opt_in.filter(Boolean).length;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Micro-enterprises (Tier 2)</CardTitle>
          <CardDescription><span className="num">{optIn}</span> of <span className="num">{e.id.length}</span> workshops opted in to shifting motor load. The rest are never touched.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-2 sm:grid-cols-7 lg:grid-cols-12">
          {e.id.map((id, i) => (
            <div key={id} className="rounded-md border bg-background/40 px-2 py-1.5 text-[11.5px]">
              <div className="num">{id}</div>
              <div className={e.opt_in[i] ? "text-primary" : "text-faint"}>{e.opt_in[i] ? "Opted in" : "Not shifted"}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
