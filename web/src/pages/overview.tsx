import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { CityView, FeederInset, FeederStateLine } from "@/components/city/city-view";
import { PlaybackBar } from "@/components/city/playback";
import { Kpi } from "@/components/kpi";
import { Legend, TimeChart } from "@/components/charts/time-chart";
import { useCity, useFeeder, useMeta, useSummary } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { f0, f1 } from "@/lib/format";
import type { CityScenario, Variant } from "@/lib/types";
import { cn, sum } from "@/lib/utils";

export default function Overview() {
  const scen = useUI((s) => s.cityScenario);
  const variant = useUI((s) => s.variant);
  const { setCityScenario, setVariant } = useUI.getState();
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          <CityView />
          <PlaybackBar />
        </div>
        <LiveCity />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Pilot feeder F07, 420 homes</CardTitle>
              <CardDescription>Amber homes are fully supplied, teal outlines are Tier-3 appliances paused by the fairness ledger, dark homes have no supply.</CardDescription>
            </div>
            <Segmented<Variant> label="GridSetu variant" size="sm" value={variant === "baseline" ? "gridsetu" : variant}
              onChange={setVariant} options={[
                { value: "gridsetu", label: "GridSetu", title: "GridSetu on the baseline city" },
                { value: "gridsetu_coordinated", label: "With city DR", title: "Adds solar-hour irrigation and industrial demand response" },
              ]} />
          </CardHeader>
          <CardContent className="space-y-3">
            <FeederInset />
            <FeederStateLine />
          </CardContent>
        </Card>
        <MonthlyKpis />
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Demand and supply, this week</CardTitle>
            <CardDescription>Click anywhere on a chart to move the playhead there.</CardDescription>
          </div>
          <Segmented<CityScenario> label="City scenario" size="sm" value={scen} onChange={setCityScenario} options={[
            { value: "baseline", label: "Baseline city" },
            { value: "coordinated", label: "Coordinated city", title: "Solar-hour irrigation and industrial demand response" },
          ]} />
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-2">
          <CityBalanceChart />
          <FeederImportChart />
        </CardContent>
      </Card>
    </div>
  );
}

function LiveCity() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  const { data: meta } = useMeta();
  if (!city || !meta) return <Skeleton className="h-full min-h-80" />;
  const s = city.scenarios[scen];
  const regions = Object.keys(meta.config.regions);
  const demand = regions.reduce((a, r) => a + sum(Object.values(s.load[r]), step), 0);
  const shed = regions.reduce((a, r) => a + sum(Object.values(s.shed[r]), step), 0);
  const gen = Object.values(s.gen);
  const supply = sum(gen, step);
  const csi = city.weather.csi[step] ?? 0;
  const rows: [string, string, string?][] = [
    ["City demand", `${f0(demand)} MW`],
    ["Served", `${f0(demand - shed)} MW`, shed > 0.5 ? `${f0(shed)} MW shed` : undefined],
    ["Generation + import", `${f0(supply)} MW`],
    ["National import", `${f0(s.gen.IMP[step])} MW`],
    ["Solar park", `${f0(s.gen.S1[step])} MW`],
    ["Wind farm", `${f0(s.gen.W1[step])} MW`],
    ["Sky", csi > 0.75 ? "Clear" : csi > 0.5 ? "Broken cloud" : "Overcast monsoon"],
  ];
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-1"><CardTitle>Live, at the playhead</CardTitle></CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <dl className="divide-y divide-border/70">
          {rows.map(([k, v, extra]) => (
            <div key={k} className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="text-right">
                <span className="num">{v}</span>
                {extra && <div className="text-[12px] font-medium text-amber">{extra}</div>}
              </dd>
            </div>
          ))}
        </dl>
        <div>
          <div className="mb-1.5 text-[12.5px] text-muted-foreground">Real-time price by region</div>
          <div className="grid grid-cols-3 gap-2">
            {regions.map((r, i) => (
              <div key={r} className="rounded-md bg-raised/60 px-2 py-1.5">
                <div className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                  <i className="size-2 rounded-full" style={{ background: `var(--r${i + 1})` }} />{r}
                </div>
                <div className={cn("num text-[15px]", (s.price_rt[r][step] ?? 0) >= meta.config.price_cap - 0.01 && "text-amber")}>
                  ₹{f1(s.price_rt[r][step])}
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-auto text-[12px] leading-relaxed text-muted-foreground">
          Space plays or pauses. Arrow keys step 15 minutes, with Shift an hour.
        </p>
      </CardContent>
    </Card>
  );
}

function MonthlyKpis() {
  const { data: s } = useSummary();
  if (!s) return <Skeleton className="h-full min-h-72" />;
  const b = s.monthly.baseline, g = s.monthly.gridsetu;
  const seeds = s.monthly.baseline.critical_outage_hours.max !== s.monthly.baseline.critical_outage_hours.min;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>A typical month on F07</CardTitle>
          <CardDescription>Three normal weeks and one stress week{seeds ? ", averaged over seeds" : ""}. Simulated on synthetic data.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-5 gap-y-5">
        <Kpi label="Critical-load outage" unit="h" format={f1} value={g.critical_outage_hours.mean} baseline={b.critical_outage_hours.mean} />
        <Kpi label="Evening-ramp unserved" unit="kWh" hint="17:30 to 19:30" format={f0} value={g.evening_window_unserved_kwh.mean} baseline={b.evening_window_unserved_kwh.mean} />
        <Kpi label="Whole feeder dark" unit="h" format={f1} value={g.feeder_outage_hours.mean} baseline={b.feeder_outage_hours.mean} />
        <Kpi label="Peak drawn from the grid" unit="kW" format={f0} value={g.feeder_peak_import_kw.mean} baseline={b.feeder_peak_import_kw.mean} />
        <Kpi label="Transformer overload trips" format={f0} value={g.overload_trips.mean} baseline={b.overload_trips.mean} />
        <Kpi label="Battery cycles" format={f1} value={g.battery_cycles.mean} better="higher" />
      </CardContent>
    </Card>
  );
}

function CityBalanceChart() {
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  const series = useMemo(() => {
    if (!city) return null;
    const s = city.scenarios[scen];
    const rs = Object.keys(s.load);
    const demand = city.weather.csi.map((_, i) => rs.reduce((a, r) => a + sum(Object.values(s.load[r]), i), 0));
    const shed = city.weather.csi.map((_, i) => rs.reduce((a, r) => a + sum(Object.values(s.shed[r]), i), 0));
    const ren = city.weather.csi.map((_, i) => (s.gen.S1[i] ?? 0) + (s.gen.W1[i] ?? 0) + rs.reduce((a, r) => a + (s.rooftop[r][i] ?? 0), 0));
    return { demand, served: demand.map((d, i) => d - shed[i]), ren, shedMask: shed.map((x) => x > 0.05) };
  }, [city, scen]);
  if (!city || !series) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h4 className="text-[13px] font-medium">City demand, served load and renewables</h4>
        <Legend items={[{ label: "Demand", color: "--foreground" }, { label: "Served", color: "--series-gridsetu" },
          { label: "Solar + wind", color: "--amber-fill" }, { label: "Shedding", color: "--amber-fill", area: true }]} />
      </div>
      <TimeChart ariaLabel="City demand, served load and renewable output over the week" t0={city.t0} yLabel="MW"
        height={230} shade={[{ mask: series.shedMask, color: "--amber-fill/0.18", label: "Shedding" }]}
        series={[
          { label: "Demand", values: series.demand, color: "--foreground", width: 1.25, unit: "MW" },
          { label: "Served", values: series.served, color: "--series-gridsetu", width: 1.75, unit: "MW" },
          { label: "Solar + wind", values: series.ren, color: "--amber-fill", width: 1.25, unit: "MW" },
        ]} />
    </div>
  );
}

function FeederImportChart() {
  const week = useUI((s) => s.week);
  const variant = useUI((s) => s.variant);
  const { data: f } = useFeeder(week);
  const right = variant === "baseline" ? "gridsetu" : variant;
  const series = useMemo(() => f && ([
    { label: "Baseline", values: f.variants.baseline.series.import, color: "--series-baseline", unit: "kW" },
    { label: "GridSetu", values: f.variants[right].series.import, color: "--series-gridsetu", width: 2, unit: "kW" },
  ]), [f, right]);
  const dark = useMemo(() => f?.variants.baseline.state.map((c) => {
    const st = f.state_codes[c]; return st.includes("trip") && st !== "overload_event";
  }) ?? [], [f]);
  if (!f || !series) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h4 className="text-[13px] font-medium">Power drawn by the pilot feeder</h4>
        <Legend items={[{ label: "Baseline", color: "--series-baseline" }, { label: "GridSetu", color: "--series-gridsetu" },
          { label: "Baseline dark", color: "--danger/0.25", area: true }]} />
      </div>
      <TimeChart ariaLabel="Pilot feeder import, baseline versus GridSetu" t0={f.t0} yLabel="kW" height={230}
        refLines={[{ y: f.capacity_kw, label: `Transformer rating ${f.capacity_kw} kW` }]}
        shade={[{ mask: dark, color: "--danger/0.16", label: "Baseline dark" }]} series={series} />
    </div>
  );
}
