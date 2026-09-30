import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon } from "@/components/icon";
import { Kpi } from "@/components/kpi";
import { DataTable, type Column } from "@/components/data-table";
import { PlaybackBar } from "@/components/city/playback";
import { useCanvasLoop } from "@/components/city/city-view";
import { MapScene } from "@/components/fleet/map-scene";
import { useActiveRun, useCity, useFleet, useMap, useMeta } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { f0, f1, fmtDay, fmtHM, stepDate, STATE_LABEL } from "@/lib/format";
import type { FleetCurvePoint, FleetFeederRow, FleetPayload } from "@/lib/types";
import { cn, decodeB64 } from "@/lib/utils";

const LEVELS = ["0", "0.25", "0.5", "0.75", "1"] as const;
type Level = (typeof LEVELS)[number];

function adoptedSet(fleet: FleetPayload | undefined, level: number): Set<number> {
  if (!fleet) return new Set();
  const k = Math.round(level * fleet.feeders.length);
  return new Set(fleet.feeders.filter((f) => f.rank < k).map((f) => f.group));
}

export default function FleetPage() {
  const week = useUI((s) => s.week);
  const fleet = useFleet(week);
  const map = useMap();
  const { run } = useActiveRun();
  const [level, setLevel] = useState<Level>("0.5");
  const [selected, setSelected] = useState<number | null>(7);
  const lvl = Number(level);

  if (fleet.metaLoaded && !fleet.available) {
    return (
      <Card className="mx-auto mt-10 max-w-xl">
        <CardContent className="space-y-2 py-8 text-center">
          <Icon name="map" className="mx-auto size-6 text-muted-foreground" />
          <p className="text-[14px] font-medium">This run has no fleet study</p>
          <p className="text-[13px] text-muted-foreground">
            {run?.label ?? "This run"} was computed without the city-wide studies. Pick the reference scenario from
            the run menu at the top right to see all 20 feeders.
          </p>
        </CardContent>
      </Card>
    );
  }
  const data = fleet.data;
  const point = data?.curve.find((c) => Math.abs(c.adoption - lvl) < 1e-6);
  const zero = data?.curve[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[74ch] text-[13.5px] leading-relaxed text-muted-foreground">
          R3 has 20 domestic feeders that the DISCOM rotates through when it sheds load. Choose how many run
          GridSetu. The rollout starts with overloaded transformers, then feeders with a clinic or school.
        </p>
        <Segmented<Level> label="GridSetu adoption" value={level} onChange={setLevel} options={LEVELS.map((v) => ({
          value: v, label: `${Math.round(Number(v) * 100)}%`,
          title: `${Math.round(Number(v) * 20)} of 20 feeders`,
        }))} />
      </div>

      <Card>
        <CardContent className="grid grid-cols-2 gap-5 pt-4 @[31rem]:grid-cols-5">
          {point && zero ? (<>
            <Kpi label="Critical sites without power" unit="site-h" format={f0} value={point.critical_site_hours} baseline={zero.critical_site_hours} hint="Clinic, school, pump and street-light hours dark this week" />
            <Kpi label="Homes dark" unit="home-h" format={f0} value={point.household_dark_hours} baseline={zero.household_dark_hours} />
            <Kpi label="Unserved energy" unit="kWh" format={f0} value={point.total_unserved_kwh} baseline={zero.total_unserved_kwh} />
            <Kpi label="Transformer overload trips" format={f0} value={point.overload_trips} baseline={zero.overload_trips} />
            <Kpi label="Community batteries" unit="kWh" format={f0} value={point.batteries_kwh} better="higher" hint={`${point.feeders} feeders with GridSetu`} />
          </>) : Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-16" />)}
        </CardContent>
      </Card>

      <div className="grid gap-4 @[62rem]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-3">
          <MapView level={lvl} selected={selected} onSelect={setSelected} />
          <MapLegend />
          <PlaybackBar />
        </div>
        <FeederDetail fleet={data} group={selected} level={lvl} />
      </div>

      <AdoptionCurves curve={data?.curve} level={lvl} onPick={(v) => setLevel(String(v) as Level)} />
      <FeederTable fleet={data} level={lvl} onPick={setSelected} />
      {data && (
        <p className="text-[12.5px] text-muted-foreground">
          {map.data?.source === "osm" ? map.data.attribution : "Streets are generated. Run `gridsetu fetch-osm` on a machine with internet to draw real OpenStreetMap streets."}
          {" "}Feeders do not affect each other here: every DISCOM request is a share of that feeder's own load, so
          adopting on one feeder cannot push shedding onto another.
        </p>
      )}
    </div>
  );
}

function MapView({ level, selected, onSelect }: { level: number; selected: number | null; onSelect: (g: number) => void }) {
  const week = useUI((s) => s.week);
  const { data: fleet } = useFleet(week);
  const { data: map } = useMap();
  const { data: city } = useCity(week);
  const { data: meta } = useMeta();
  const canvas = useRef<HTMLCanvasElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const decoded = useMemo(() => fleet && {
    baseline: decodeB64(fleet.states_b64.baseline), gridsetu: decodeB64(fleet.states_b64.gridsetu) }, [fleet]);
  const adopted = useMemo(() => adoptedSet(fleet, level), [fleet, level]);
  const holder = useRef<{ scene: MapScene | null }>({ scene: null });
  const scene = useCanvasLoop(canvas, (c) => {
    const s = new MapScene(c);
    holder.current.scene = s;
    return { render: (st, dt) => s.render(st, dt), resize: (w) => s.resize(w), onTheme: () => s.onTheme() };
  }, []);

  useEffect(() => {
    const s = holder.current.scene;
    if (!s) return;
    s.setData(map ?? null, fleet ?? null, city ?? null);
    if (meta) s.regionName = Object.fromEntries(Object.entries(meta.config.regions).map(([k, v]) => [k, v.name]));
    const parent = canvas.current?.parentElement;
    if (parent) s.resize(parent.clientWidth);
  }, [map, fleet, city, meta, scene]);
  useEffect(() => { holder.current.scene?.setAdopted(adopted); }, [adopted, scene]);
  useEffect(() => { if (holder.current.scene) holder.current.scene.selected = selected; }, [selected]);

  const onMove = (e: React.PointerEvent) => {
    const s = holder.current.scene, t = tip.current;
    if (!s || !t || !fleet || !decoded) return;
    const r = canvas.current!.getBoundingClientRect();
    const hit = s.hitTest(e.clientX - r.left, e.clientY - r.top);
    s.hover = hit?.group ?? null;
    canvas.current!.style.cursor = hit ? "pointer" : "default";
    if (!hit) { t.style.opacity = "0"; return; }
    const row = fleet.feeders.find((f) => f.group === hit.group);
    if (!row) return;
    const mode = adopted.has(row.group) ? "gridsetu" : "baseline";
    const idx = fleet.feeders.indexOf(row);
    const step = Math.floor(useUI.getState().step);
    const st = fleet.state_codes[decoded[mode][idx * fleet.n + step]] ?? "normal";
    t.innerHTML = `<div style="font-weight:600">${row.id}${row.is_pilot ? " · pilot" : ""}</div>
      <div style="color:var(--muted-foreground)">${row.households} homes · ${mode === "gridsetu" ? "GridSetu" : "no GridSetu"}</div>
      <div style="margin-top:3px">${STATE_LABEL[st] ?? st}</div>`;
    const x = Math.min(hit.x + 16, r.width - 230);
    t.style.transform = `translate(${x}px, ${Math.max(8, hit.y - 30)}px)`;
    t.style.opacity = "1";
  };
  const onClick = (e: React.MouseEvent) => {
    const s = holder.current.scene;
    if (!s) return;
    const r = canvas.current!.getBoundingClientRect();
    const hit = s.hitTest(e.clientX - r.left, e.clientY - r.top);
    if (hit) onSelect(hit.group);
  };

  return (
    <div className="relative overflow-hidden rounded-lg border bg-background">
      <canvas ref={canvas} className="block w-full" role="img" onPointerMove={onMove}
        onPointerLeave={() => { if (tip.current) tip.current.style.opacity = "0"; if (holder.current.scene) holder.current.scene.hover = null; }}
        onClick={onClick}
        aria-label="City map: plants, 220 kV lines, and the 20 R3 feeders coloured by their state at the playhead" />
      {(!map || !fleet) && <Skeleton className="absolute inset-0 rounded-none" />}
      <div ref={tip} aria-hidden
        className="pointer-events-none absolute left-0 top-0 z-10 w-56 rounded-md border bg-raised/95 px-2.5 py-2 text-[12px] leading-5 opacity-0 shadow-lg backdrop-blur transition-opacity duration-100" />
    </div>
  );
}

function MapClock() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const { data: city } = useCity(week);
  if (!city) return null;
  const d = stepDate(city.t0, city.dt_min, step);
  return (
    <span className="mr-auto inline-flex items-baseline gap-2 text-foreground">
      <span className="font-display text-[24px] leading-none">{fmtHM(d)}</span>
      <span className="text-muted-foreground">{fmtDay(d)}</span>
    </span>
  );
}

function MapLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <MapClock />
      <span className="inline-flex items-center gap-2"><i className="size-2 rounded-[2px] bg-amber-fill" />Homes supplied</span>
      <span className="inline-flex items-center gap-2"><i className="size-2 rounded-[2px] bg-raised ring-1 ring-border" />Homes dark</span>
      <span className="inline-flex items-center gap-2"><i className="size-2.5 rounded-full ring-2 ring-primary" />Runs GridSetu</span>
      <span className="inline-flex items-center gap-2"><b className="w-2 text-center text-primary">+</b>Critical site islanded</span>
      <span className="inline-flex items-center gap-2"><b className="w-2 text-center text-danger">+</b>Critical site dark</span>
    </div>
  );
}

function FeederDetail({ fleet, group, level }: { fleet: FleetPayload | undefined; group: number | null; level: number }) {
  const row = fleet?.feeders.find((f) => f.group === group);
  if (!fleet) return <Skeleton className="h-full min-h-80" />;
  if (!row) {
    return (
      <Card className="self-start"><CardContent className="py-8 text-center text-[13px] text-muted-foreground">
        Select a feeder on the map to see its week.
      </CardContent></Card>
    );
  }
  const adopted = adoptedSet(fleet, level).has(row.group);
  const crit = Object.entries(row.critical).filter(([, v]) => v > 0.01).map(([k]) => k.replace(/_/g, " ").replace("core", "").trim());
  const rows: [string, keyof FleetFeederRow["baseline"], (v: number) => string][] = [
    ["Critical-load outage", "critical_outage_hours", (v) => `${f1(v)} h`],
    ["Whole feeder dark", "feeder_outage_hours", (v) => `${f1(v)} h`],
    ["Homes dark", "household_dark_hours", (v) => `${f0(v)} home-h`],
    ["Unserved energy", "total_unserved_kwh", (v) => `${f0(v)} kWh`],
    ["Overload trips", "overload_trips", f0],
    ["Peak from the grid", "peak_import_kw", (v) => `${f0(v)} kW`],
  ];
  return (
    <Card className="self-start">
      <CardHeader>
        <div>
          <CardTitle>{row.id}{row.is_pilot && " (pilot)"}</CardTitle>
          <CardDescription>
            {row.households} homes · peak {f0(row.peak_kw)} kW on a {f0(row.rating_kw)} kW transformer
          </CardDescription>
        </div>
        <Badge tone={adopted ? "teal" : "neutral"}>{adopted ? "GridSetu" : "Not yet"}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {crit.map((c) => <Badge key={c} tone="outline" className="capitalize">{c}</Badge>)}
          {row.sps_member && <Badge tone="amber">In the SPS block</Badge>}
        </div>
        <p className="text-[12.5px] text-muted-foreground">
          Battery if adopted: <span className="num">{f0(row.battery_kwh)} kWh / {f0(row.battery_kw)} kW</span>.
          Rollout order <span className="num">{row.rank + 1}</span> of 20.
        </p>
        <table className="w-full text-[12.5px]">
          <thead className="text-left text-muted-foreground">
            <tr className="border-b"><th className="py-1.5 font-medium">This week</th><th className="text-right font-medium">Baseline</th><th className="text-right font-medium">GridSetu</th></tr>
          </thead>
          <tbody>
            {rows.map(([label, k, fmt]) => (
              <tr key={k} className="border-b border-border/60">
                <td className="py-1.5">{label}</td>
                <td className={cn("num text-right", !adopted && "text-foreground", adopted && "text-muted-foreground")}>{fmt(row.baseline[k])}</td>
                <td className={cn("num text-right", adopted ? "text-primary" : "text-muted-foreground")}>{fmt(row.gridsetu[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

const CURVES: { key: keyof FleetCurvePoint; label: string; unit: string }[] = [
  { key: "critical_site_hours", label: "Critical sites without power", unit: "site-hours" },
  { key: "household_dark_hours", label: "Homes dark", unit: "home-hours" },
  { key: "total_unserved_kwh", label: "Unserved energy", unit: "kWh" },
  { key: "overload_trips", label: "Transformer overload trips", unit: "trips" },
];

function AdoptionCurves({ curve, level, onPick }: { curve?: FleetCurvePoint[]; level: number; onPick: (v: number) => void }) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>What each step of the rollout buys</CardTitle>
          <CardDescription>The week's totals across all 20 feeders at each adoption level. Select a bar to show that level on the map.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 @[38rem]:grid-cols-2 @[62rem]:grid-cols-4">
        {!curve ? CURVES.map((c) => <Skeleton key={c.key} className="h-44" />) : CURVES.map((c) => (
          <MiniBars key={c.key} title={c.label} unit={c.unit} level={level} onPick={onPick}
            points={curve.map((p) => ({ x: p.adoption, y: Number(p[c.key]) }))} />
        ))}
      </CardContent>
    </Card>
  );
}

function MiniBars({ title, unit, points, level, onPick }: {
  title: string; unit: string; points: { x: number; y: number }[]; level: number; onPick: (v: number) => void;
}) {
  const max = Math.max(...points.map((p) => p.y), 1);
  const W = 260, H = 130, pad = 22, bw = (W - 8) / points.length - 8;
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 flex items-baseline justify-between gap-2 text-[13px]">
        <span className="font-medium">{title}</span><span className="text-[11.5px] text-muted-foreground">{unit}</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H + pad}`} className="w-full overflow-visible" role="img"
        aria-label={`${title} by adoption level: ${points.map((p) => `${Math.round(p.x * 100)}% ${Math.round(p.y)}`).join(", ")}`}>
        <line x1={0} x2={W} y1={H} y2={H} stroke="var(--border)" />
        {points.map((p, i) => {
          const h = (p.y / max) * (H - 18);
          const x = 4 + i * (bw + 8);
          const on = Math.abs(p.x - level) < 1e-6;
          return (
            <g key={p.x} className="cursor-pointer" onClick={() => onPick(p.x)}>
              <rect x={x} y={0} width={bw} height={H} fill="transparent" />
              <rect x={x} y={H - h} width={bw} height={Math.max(h, 1)} rx={3}
                fill={on ? "var(--series-gridsetu)" : "var(--series-baseline)"} opacity={on ? 1 : 0.55}
                className="transition-[opacity] duration-100 hover:opacity-90" />
              <text x={x + bw / 2} y={H - h - 5} textAnchor="middle" fontSize={11} fill="var(--foreground)"
                className="num">{p.y >= 1000 ? `${(p.y / 1000).toFixed(1)}k` : Math.round(p.y)}</text>
              <text x={x + bw / 2} y={H + 15} textAnchor="middle" fontSize={11}
                fill={on ? "var(--foreground)" : "var(--muted-foreground)"}>{Math.round(p.x * 100)}%</text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

function FeederTable({ fleet, level, onPick }: { fleet?: FleetPayload; level: number; onPick: (g: number) => void }) {
  const adopted = useMemo(() => adoptedSet(fleet, level), [fleet, level]);
  const cols = useMemo<Column<FleetFeederRow>[]>(() => [
    { key: "id", header: "Feeder", width: "96px", value: (r) => r.id, mono: true,
      cell: (r) => <span className="inline-flex items-center gap-1.5"><i className={cn("size-2 rounded-full", adopted.has(r.group) ? "bg-primary" : "bg-raised ring-1 ring-border")} />{r.id}</span> },
    { key: "rank", header: "Rollout", width: "88px", value: (r) => r.rank, align: "right", mono: true, cell: (r) => r.rank + 1 },
    { key: "households", header: "Homes", width: "84px", value: (r) => r.households, align: "right", mono: true },
    { key: "load", header: "Peak / rating", width: "120px", value: (r) => r.peak_kw / r.rating_kw, align: "right", mono: true,
      cell: (r) => <span className={r.peak_kw > r.rating_kw ? "text-amber" : undefined}>{Math.round((100 * r.peak_kw) / r.rating_kw)}%</span> },
    { key: "crit", header: "Critical sites", width: "112px", value: (r) => r.baseline.critical_sites, align: "right", mono: true },
    { key: "cb", header: "Critical h, base", width: "132px", value: (r) => r.baseline.critical_outage_hours, align: "right", mono: true, cell: (r) => f1(r.baseline.critical_outage_hours) },
    { key: "cg", header: "Critical h, Setu", width: "132px", value: (r) => r.gridsetu.critical_outage_hours, align: "right", mono: true, cell: (r) => f1(r.gridsetu.critical_outage_hours) },
    { key: "db", header: "Dark h, base", width: "116px", value: (r) => r.baseline.feeder_outage_hours, align: "right", mono: true, cell: (r) => f1(r.baseline.feeder_outage_hours) },
    { key: "dg", header: "Dark h, Setu", width: "116px", value: (r) => r.gridsetu.feeder_outage_hours, align: "right", mono: true, cell: (r) => f1(r.gridsetu.feeder_outage_hours) },
    { key: "bat", header: "Battery", width: "minmax(100px,1fr)", value: (r) => r.battery_kwh, align: "right", mono: true, cell: (r) => `${f0(r.battery_kwh)} kWh` },
  ], [adopted]);
  if (!fleet) return <Skeleton className="h-80" />;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>All 20 feeders</CardTitle>
          <CardDescription>Each feeder simulated under both controllers against the same city week. Select a row to show it on the map.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable label="R3 feeders" rows={fleet.feeders} columns={cols} height={420} minWidth={1100}
          initialSort={{ key: "rank", dir: 1 }} onRowClick={(r) => onPick(r.group)} />
      </CardContent>
    </Card>
  );
}
