import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Legend, TimeChart, type ChartSeries } from "@/components/charts/time-chart";
import { PairBar } from "@/components/charts/spark";
import { useCity, useIsland, useMeta, useSummary } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { f0, f1, f2, pct } from "@/lib/format";
import type { CityScenario } from "@/lib/types";

const KINDS: [string, string, string][] = [
  ["thermal", "Coal", "--c-traction"], ["gas", "Gas", "--c-municipal"], ["hydro", "Hydro", "--c-domestic"],
  ["import", "National import", "--c-commercial"], ["wind", "Wind", "--c-irrigation"], ["solar", "Solar", "--c-industrial"],
];
const CLASS_COLORS: Record<string, string> = {
  traction: "--c-traction", municipal: "--c-municipal", domestic: "--c-domestic",
  commercial: "--c-commercial", irrigation: "--c-irrigation", industrial: "--c-industrial",
};

export default function CityPage() {
  const scen = useUI((s) => s.cityScenario);
  const { setCityScenario } = useUI.getState();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[70ch] text-[13.5px] leading-relaxed text-muted-foreground">
          Three bid areas clear a day-ahead market in 96 fifteen-minute blocks, then re-dispatch in real time.
          When supply runs short, the DISCOM sheds by priority: irrigation first, then homes, then shops and
          industry. Railways and municipal water are never cut.
        </p>
        <Segmented<CityScenario> label="City scenario" value={scen} onChange={setCityScenario} options={[
          { value: "baseline", label: "Baseline city" },
          { value: "coordinated", label: "Coordinated city", title: "Solar-hour irrigation and industrial DR" },
        ]} />
      </div>
      <Dispatch />
      <div className="grid gap-4 lg:grid-cols-2">
        <Prices />
        <Flows />
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Shedding />
        <SystemFactors />
      </div>
      <ClassFactors />
      <PlantFactors />
      <Island />
    </div>
  );
}

function Dispatch() {
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  const { data: meta } = useMeta();
  const built = useMemo(() => {
    if (!city || !meta) return null;
    const s = city.scenarios[scen];
    const n = city.n;
    const byKind = KINDS.map(([k]) => {
      const units = Object.entries(meta.config.generators).filter(([, g]) => g.kind === k).map(([id]) => id);
      return Array.from({ length: n }, (_, i) => units.reduce((a, u) => a + (s.gen[u]?.[i] ?? 0), 0));
    });
    const cum: number[][] = [];
    byKind.forEach((arr, j) => cum.push(arr.map((v, i) => v + (j ? cum[j - 1][i] : 0))));
    const rs = Object.keys(s.load);
    const demand = Array.from({ length: n }, (_, i) =>
      rs.reduce((a, r) => a + Object.values(s.load[r]).reduce((b, x) => b + (x[i] ?? 0), 0) - (s.rooftop[r][i] ?? 0), 0));
    const shed = Array.from({ length: n }, (_, i) =>
      rs.reduce((a, r) => a + Object.values(s.shed[r]).reduce((b, x) => b + (x[i] ?? 0), 0), 0));
    // draw the tallest stack first; each later (smaller) cumulative paints over it
    const series: ChartSeries[] = KINDS.map(([, label, color], j) => ({ label, values: cum[j], color, fill: `${color}/0.55`, width: 1, unit: "MW" })).reverse();
    const raw = byKind.slice().reverse();
    series.push({ label: "Net demand", values: demand, color: "--foreground", width: 1.5, unit: "MW" });
    raw.push(demand);
    return { series, raw, shed: shed.map((x) => x > 0.05) };
  }, [city, meta, scen]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Where the power came from</CardTitle>
          <CardDescription>Real-time dispatch by source against net demand (after rooftop solar). Shaded spans had load shedding.</CardDescription>
        </div>
        <Legend items={[...KINDS.map(([, l, c]) => ({ label: l, color: c, area: true })), { label: "Net demand", color: "--foreground" }]} />
      </CardHeader>
      <CardContent>
        {built && city ? (
          <TimeChart ariaLabel="Stacked generation by source over the week" t0={city.t0} yLabel="MW" height={280}
            series={built.series} tooltipValues={built.raw}
            shade={[{ mask: built.shed, color: "--danger/0.12", label: "Shedding" }]} />
        ) : <Skeleton className="h-[280px]" />}
      </CardContent>
    </Card>
  );
}

function Prices() {
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  const { data: meta } = useMeta();
  const series = useMemo(() => city && meta && Object.keys(meta.config.regions).map((r, i) => ({
    label: `${r} ${meta.config.regions[r].name}`, values: city.scenarios[scen].price_da[r],
    color: `--r${i + 1}`, width: [3.2, 2.2, 1.3][i], unit: "₹/kWh",
  })), [city, meta, scen]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Day-ahead market clearing price</CardTitle>
          <CardDescription>Areas share one price unless an intertie is congested. The exchange ceiling is ₹{meta?.config.price_cap ?? 10}/kWh.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {series && <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />}
        {series && city ? (
          <TimeChart ariaLabel="Regional market clearing price" t0={city.t0} yLabel="₹/kWh" height={210} yMin={0}
            yMax={(meta?.config.price_cap ?? 10) * 1.12} valueFormat={f2}
            refLines={[{ y: meta?.config.price_cap ?? 10, label: "Price ceiling" }]} series={series} />
        ) : <Skeleton className="h-[210px]" />}
      </CardContent>
    </Card>
  );
}

function Flows() {
  const week = useUI((s) => s.week);
  const scen = useUI((s) => s.cityScenario);
  const { data: city } = useCity(week);
  const series = useMemo(() => city && Object.entries(city.scenarios[scen].flow).map(([k, v], i) => ({
    label: k, values: v.map((x) => (x == null ? null : (Math.abs(x) / city.tie_limit[k]) * 100)),
    color: `--r${i + 1}`, unit: "%",
  })), [city, scen]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Intertie loading</CardTitle>
          <CardDescription>Market flow on each 220 kV intertie as a share of its transfer capability.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {series && <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />}
        {series && city ? (
          <TimeChart ariaLabel="Intertie loading as a share of transfer capability" t0={city.t0} yLabel="%" height={210}
            yMin={0} yMax={112} refLines={[{ y: 100, label: "Transfer capability" }]} series={series} />
        ) : <Skeleton className="h-[210px]" />}
      </CardContent>
    </Card>
  );
}

function Shedding() {
  const week = useUI((s) => s.week);
  const { data: s } = useSummary();
  if (!s) return <Skeleton className="h-72" />;
  const b = s.city[week].baseline, c = s.city[week].coordinated;
  const classes = Object.keys(b.ens_by_class_mwh);
  const max = Math.max(...classes.map((k) => Math.max(b.ens_by_class_mwh[k], c.ens_by_class_mwh[k])), 1);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Energy not served, by consumer class</CardTitle>
          <CardDescription>
            <span className="num">{f0(b.energy_not_served_mwh)}</span> MWh baseline, <span className="num">{f0(c.energy_not_served_mwh)}</span> MWh with solar-hour irrigation and industrial demand response.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {classes.map((k) => (
          <div key={k} className="grid grid-cols-[92px_1fr] items-center gap-3">
            <div className="flex items-center gap-2 text-[13px] capitalize">
              <i className="size-2 rounded-full" style={{ background: `var(${CLASS_COLORS[k]})` }} />{k}
            </div>
            <PairBar baseline={b.ens_by_class_mwh[k]} gridsetu={c.ens_by_class_mwh[k]} max={max} fmt={(v) => `${f0(v)} MWh`}
              labels={["Baseline", "Coordinated"]} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SystemFactors() {
  const { data: s } = useSummary();
  const week = useUI((st) => st.week);
  if (!s) return <Skeleton className="h-72" />;
  const f = s.system_factors;
  const m = s.city[week].baseline;
  const rows: [string, string][] = [
    ["City peak demand", `${f0(f.city_peak_mw)} MW`],
    ["Installed capacity", `${f0(f.installed_capacity_mw)} MW`],
    ["Load factor", f2(f.city_load_factor)],
    ["Diversity factor across regions", f2(f.diversity_factor_regions)],
    ["Utilisation factor", f2(f.utilisation_factor)],
    ["Reserve margin at peak", pct(f.reserve_margin_at_peak_pct, 1)],
    ["Renewable share of energy", pct(m.renewable_share_pct, 1)],
    ["Hours with shedding", `${f1(m.shedding_hours)} h`],
    ["Hours at the price ceiling", `${f1(m.scarcity_hours)} h`],
  ];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>System planning factors</CardTitle>
          <CardDescription>Stress-week network, baseline dispatch.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border/70">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between py-1.5 text-[13px]">
              <dt className="text-muted-foreground">{k}</dt><dd className="num">{v}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function ClassFactors() {
  const { data: s } = useSummary();
  if (!s) return <Skeleton className="h-64" />;
  const rows = s.class_factors.filter((r) => r.region === "CITY");
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Load classes</CardTitle>
          <CardDescription>Priority 1 is never shed. Connected load is derived from each class's demand factor.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead className="text-left text-[12px] text-muted-foreground">
            <tr className="border-b">
              {["Class", "Priority", "Max demand", "Average", "Connected load", "Load factor", "Demand factor", "Diversity factor"].map((h, i) => (
                <th key={h} className={`py-2 font-medium ${i > 1 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.sort((a, b) => a.priority - b.priority).map((r) => (
              <tr key={r.class} className="border-b border-border/60 transition-colors duration-100 hover:bg-raised/40">
                <td className="py-2 capitalize"><span className="inline-flex items-center gap-2">
                  <i className="size-2 rounded-full" style={{ background: `var(${CLASS_COLORS[r.class]})` }} />{r.class}</span></td>
                <td className="num">{r.priority}</td>
                <td className="num text-right">{f0(r.max_demand_mw)} MW</td>
                <td className="num text-right">{f0(r.avg_demand_mw)} MW</td>
                <td className="num text-right">{f0(r.connected_load_mw)} MW</td>
                <td className="num text-right">{f2(r.load_factor)}</td>
                <td className="num text-right">{f2(r.demand_factor)}</td>
                <td className="num text-right">{f2(r.diversity_factor ?? 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function PlantFactors() {
  const { data: s } = useSummary();
  if (!s) return <Skeleton className="h-56" />;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Plants</CardTitle>
          <CardDescription>Capacity factor uses the whole week; plant use factor only the hours each unit ran.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead className="text-left text-[12px] text-muted-foreground">
            <tr className="border-b">
              {["Unit", "Type", "Region", "Capacity", "Energy", "Capacity factor", "Plant use factor", "Hours running"].map((h, i) => (
                <th key={h} className={`py-2 font-medium ${i > 2 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {s.plant_factors.map((r) => (
              <tr key={r.unit} className="border-b border-border/60 transition-colors duration-100 hover:bg-raised/40">
                <td className="py-2 font-medium">{r.unit}</td>
                <td className="capitalize text-muted-foreground">{r.kind}</td>
                <td>{r.region}</td>
                <td className="num text-right">{f0(r.capacity_mw)} MW</td>
                <td className="num text-right">{f0(r.energy_mwh)} MWh</td>
                <td className="num text-right">{pct(r.capacity_factor * 100)}</td>
                <td className="num text-right">{pct(r.plant_use_factor * 100)}</td>
                <td className="num text-right">{f0(r.operating_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function Island() {
  const week = useUI((s) => s.week);
  const { data: isl } = useIsland(week);
  const { data: meta } = useMeta();
  const series = useMemo(() => isl && [
    { label: "Demand", values: isl.strategies.gridsetu.load_kw, color: "--foreground", width: 1.25, unit: "kW" },
    { label: "Solar used", values: isl.strategies.gridsetu.pv_used_kw, color: "--amber-fill", unit: "kW" },
    { label: "Diesel, legacy", values: isl.strategies.legacy.diesel_kw, color: "--series-baseline", unit: "kW" },
    { label: "Diesel, GridSetu", values: isl.strategies.gridsetu.diesel_kw, color: "--series-gridsetu", width: 2, unit: "kW" },
  ], [isl]);
  if (!isl || !series) return <Skeleton className="h-72" />;
  const L = isl.strategies.legacy.metrics, G = isl.strategies.gridsetu.metrics;
  const n = (x: number | string) => Number(x);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Isolated network: {String(meta?.config.island.name ?? "remote hamlet")}</CardTitle>
          <CardDescription>No grid connection. Legacy runs the diesel set for every gap; GridSetu covers gaps from the battery and only then starts the diesel at an efficient load.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-2">
          <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
          <TimeChart ariaLabel="Isolated microgrid dispatch" t0={isl.t0} yLabel="kW" height={220} series={series} />
        </div>
        <div className="space-y-4">
          {([["Unserved energy", "unserved_kwh", "kWh"], ["Diesel run hours", "diesel_run_hours", "h"],
             ["Solar wasted", "pv_curtailed_kwh", "kWh"], ["Diesel used", "diesel_litres", "L"]] as const).map(([label, k, u]) => (
            <div key={k}>
              <div className="mb-1 text-[12.5px] text-muted-foreground">{label}</div>
              <PairBar baseline={n(L[k])} gridsetu={n(G[k])} max={Math.max(n(L[k]), n(G[k]))} fmt={(v) => `${f0(v)} ${u}`}
                labels={["Legacy", "GridSetu"]} />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
