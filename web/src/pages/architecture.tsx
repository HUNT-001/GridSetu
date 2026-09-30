import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon } from "@/components/icon";
import { PlaybackBar } from "@/components/city/playback";
import { useCity, useFeeder, useMeta, useSummary } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { f0, f1, fmtStep, STATE_LABEL } from "@/lib/format";
import type { IconName } from "@/icons/sprite.gen";
import { cn, sum } from "@/lib/utils";

const SLICE_NAMES: Record<string, string> = {
  urllc_protection: "Protection", mmtc_ami: "Meters", control_2g4g: "Control", embb_dashboard: "Dashboards",
};

interface Layer {
  id: string; name: string; icon: IconName; what: string; parts: string[]; standards: string[];
  code: string; live: [string, string][];
}

export default function ArchitecturePage() {
  const step = useStepInt();
  const week = useUI((s) => s.week);
  const { data: meta } = useMeta();
  const { data: city } = useCity(week);
  const { data: f } = useFeeder(week);
  const { data: s } = useSummary();
  const [open, setOpen] = useState("control");
  if (!meta || !city || !f || !s) return <Skeleton className="h-[640px]" />;

  const c = city.scenarios.baseline;
  const gs = f.variants.gridsetu;
  const rs = Object.keys(meta.config.regions);
  const gen = sum(Object.values(c.gen), step);
  const shed = rs.reduce((a, r) => a + sum(Object.values(c.shed[r]), step), 0);
  const maxTie = Math.max(...Object.entries(c.flow).map(([k, v]) => (Math.abs(v[step] ?? 0) / city.tie_limit[k]) * 100));
  const st = f.state_codes[gs.state[step]] ?? "normal";
  const ami = gs.comms.find((x) => x.slice === "mmtc_ami");
  const t1h = gs.reserves.filter((r) => r.stage === "T-1h");
  const dayIdx = Math.min(Math.floor(step / 96), t1h.length - 1);

  const layers: Layer[] = [
    { id: "slice", name: "Slice layer", icon: "signal", code: "comms.py",
      what: "Separate communication slices so protection traffic is never queued behind meter reads.",
      parts: ["URLLC for protection and PMUs", "mMTC for 420 smart meters", "2G/4G control with retries", "eMBB for dashboards", "Edge fail-safe on message loss"],
      standards: ["IEC 62351-3 transport security", "IEC 62351-8 role-based access"],
      live: gs.comms.map((x) => [SLICE_NAMES[x.slice] ?? x.slice, `${f1(x.delivered_pct)}% delivered`]) },
    { id: "control", name: "Control layer", icon: "sliders-horizontal", code: "market.py, feeder.py, wams.py",
      what: "Decides who generates, who is shed, and what the feeder battery and loads do each 15 minutes.",
      parts: ["Day-ahead market splitting, 96 blocks", "Real-time redispatch", "Priority load shedding", "Feeder battery LP", "Tier 1/2/3 edge controller", "Fairness ledger", "SPS and UFLS protection"],
      standards: ["IEEE 1547-2018 islanding", "CEA UFLS settings"],
      live: [["Pilot feeder", STATE_LABEL[st] ?? st], ["City shedding now", `${f0(shed)} MW`],
        ["Industrial DR now", `${f0(city.scenarios.coordinated.dr[step] ?? 0)} MW`]] },
    { id: "management", name: "Management and monitoring", icon: "gauge", code: "forecast.py, reserve.py, metrics.py",
      what: "Forecasts, sizes the uncertainty reserve, and publishes the Reliability Reserve upstream.",
      parts: ["Quantile forecasts (LightGBM, conformal)", "Monte Carlo shortfall risk", "Reliability Reserve at five stages", "Load, diversity, demand and plant factors", "Mock ADMS/DERMS ingest"],
      standards: ["IEC 61968-5 DER group forecast", "CIM IEC 61970/61968"],
      live: [["Forecast band coverage", `${f0(s.forecast_skill.net_load.coverage_q10_q90_pct)}%`],
        ["Today's reserve confidence", t1h[dayIdx] ? `${f0(t1h[dayIdx].confidence_pct)}%` : "–"],
        ["Homes fully supplied", `${f0(gs.hh_lit_pct[step])}%`]] },
    { id: "infrastructure", name: "Infrastructure layer", icon: "cpu", code: "profiles.py, feeder.py",
      what: "The metered, measured and controllable assets on the ground.",
      parts: ["420 AMI meters at 15-minute resolution", "200 kWh / 100 kW LFP battery", "90 kWp rooftop and 60 kWp community PV", "PMUs at 50 frames/s", "Feeder edge controller"],
      standards: ["IEEE C37.118 synchrophasors", "IEC 61850 substation data"],
      live: [["Battery", `${f0(gs.series.soc_pct[step])}% charged`], ["Meter reads delivered", ami ? `${f1(ami.delivered_pct)}%` : "–"],
        ["Feeder solar now", `${f0(gs.series.solar_avail[step])} kW`]] },
    { id: "power", name: "Power layer", icon: "zap", code: "market.py, network.py, island.py",
      what: "Generation to consumer: plants, the 220 kV ring, substations, the 11 kV feeder, and an isolated hamlet.",
      parts: ["Coal, gas, hydro, solar park, wind, national import", "220 kV ring with three interties", "220/33/11 kV substations", "Six consumer classes", "Isolated solar-battery-diesel microgrid", "AC power flow (pandapower)"],
      standards: ["CEA grid standards", "IEX market splitting"],
      live: [["Generation + import", `${f0(gen)} MW`], ["Busiest intertie", `${f0(maxTie)}% loaded`],
        ["Pilot feeder draw", `${f0(gs.series.import[step])} kW`]] },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[72ch] text-[13.5px] leading-relaxed text-muted-foreground">
          Five layers, read top to bottom from communications down to copper. Each shows what it is doing at
          the playhead, <span className="num">{fmtStep(city.t0, city.dt_min, step)}</span>. Select a layer to see its parts.
        </p>
      </div>
      <div className="grid gap-4 @[62rem]:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-2">
          {layers.map((l, i) => {
            const active = open === l.id;
            return (
              <button key={l.id} type="button" onClick={() => setOpen(l.id)} aria-expanded={active}
                className={cn("group grid w-full grid-cols-[40px_minmax(0,1fr)] items-start gap-3 rounded-lg border p-3 text-left",
                  "transition-[background-color,border-color] duration-100",
                  active ? "border-primary/60 bg-raised/60" : "bg-panel hover:bg-raised/40")}
                style={{ marginLeft: `${i * 12}px`, width: `calc(100% - ${4 * 12}px)` }}>
                <span className={cn("grid size-10 place-items-center rounded-md", active ? "bg-primary text-primary-foreground" : "bg-raised text-muted-foreground")}>
                  <Icon name={l.icon} className="size-5" />
                </span>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <span className="text-[14.5px] font-semibold">{l.name}</span>
                    <span className="num text-[11.5px] text-faint">{l.code}</span>
                  </span>
                  <span className="mt-0.5 block text-[12.5px] text-muted-foreground">{l.what}</span>
                  <span className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
                    {l.live.map(([k, v]) => (
                      <span key={k} className="text-[12.5px]"><span className="text-muted-foreground">{k} </span><span className="num">{v}</span></span>
                    ))}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <LayerDetail layer={layers.find((l) => l.id === open)!} />
      </div>
      <Card><CardContent className="pt-4"><PlaybackBar /></CardContent></Card>
    </div>
  );
}

function LayerDetail({ layer }: { layer: Layer }) {
  return (
    <Card key={layer.id} className="animate-in self-start">
      <CardHeader>
        <div>
          <CardTitle>{layer.name}</CardTitle>
          <CardDescription>{layer.what}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h4 className="mb-1.5 text-[12.5px] text-muted-foreground">What runs here</h4>
          <ul className="space-y-1 text-[13px]">
            {layer.parts.map((p) => <li key={p} className="flex gap-2"><Icon name="check" className="mt-0.5 text-primary" />{p}</li>)}
          </ul>
        </div>
        <div>
          <h4 className="mb-1.5 text-[12.5px] text-muted-foreground">Standards it follows</h4>
          <div className="flex flex-wrap gap-1.5">{layer.standards.map((s) => <Badge key={s} tone="outline">{s}</Badge>)}</div>
        </div>
        <div>
          <h4 className="mb-1.5 text-[12.5px] text-muted-foreground">Source</h4>
          <p className="num text-[12.5px]">src/gridsetu/{layer.code.split(", ").join(", src/gridsetu/")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
