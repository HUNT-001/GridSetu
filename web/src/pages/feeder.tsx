import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Icon } from "@/components/icon";
import { Kpi } from "@/components/kpi";
import { Legend, TimeChart } from "@/components/charts/time-chart";
import { api, type AdmsAck, IS_DEMO } from "@/lib/api";
import { useFeeder, useMeta, useSummary } from "@/lib/queries";
import { useUI } from "@/lib/store";
import { f0, f1 } from "@/lib/format";
import type { Reserve, Variant } from "@/lib/types";
import { cn } from "@/lib/utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function FeederPage() {
  const variant = useUI((s) => s.variant);
  const right: Variant = variant === "baseline" ? "gridsetu" : variant;
  return (
    <div className="space-y-4">
      <WeekKpis right={right} />
      <div className="grid gap-4 xl:grid-cols-2">
        <ImportChart right={right} />
        <CurtailChart right={right} />
        <SocChart right={right} />
        <ForecastChart />
      </div>
      <ReserveTimeline right={right} />
      <Comms right={right} />
    </div>
  );
}

function WeekKpis({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: s } = useSummary();
  if (!s) return <Skeleton className="h-28" />;
  const b = s.weekly[week].baseline, g = s.weekly[week][right];
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-5 pt-4 sm:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Evening-ramp unserved" unit="kWh" hint="17:30 to 19:30" format={f0} value={g.evening_window_unserved_kwh} baseline={b.evening_window_unserved_kwh} />
        <Kpi label="Critical-load outage" unit="h" format={f1} value={g.critical_outage_hours} baseline={b.critical_outage_hours} />
        <Kpi label="Whole feeder dark" unit="h" format={f1} value={g.feeder_outage_hours} baseline={b.feeder_outage_hours} />
        <Kpi label="Peak from the grid" unit="kW" format={f0} value={g.feeder_peak_import_kw} baseline={b.feeder_peak_import_kw} />
        <Kpi label="Tier-3 energy paused" unit="kWh" format={f0} value={g.tier3_curtailed_kwh} hint="Shiftable share returns later as rebound" />
        <Kpi label="Battery cycles this week" format={f1} value={g.battery_cycles} />
      </CardContent>
    </Card>
  );
}

function darkMask(codes: string[], states: number[]) {
  return states.map((c) => { const st = codes[c]; return st.includes("trip") && st !== "overload_event"; });
}

function ImportChart({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const series = useMemo(() => f && [
    { label: "Baseline", values: f.variants.baseline.series.import, color: "--series-baseline", unit: "kW" },
    { label: "GridSetu", values: f.variants[right].series.import, color: "--series-gridsetu", width: 2, unit: "kW" },
    { label: "DISCOM cap", values: f.variants[right].series.cap_request, color: "--amber-fill", dash: [4, 3], unit: "kW" },
  ], [f, right]);
  const mask = useMemo(() => f && darkMask(f.state_codes, f.variants.baseline.state), [f]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Power drawn from the grid</CardTitle>
          <CardDescription>GridSetu keeps the transformer under its rating and meets DISCOM caps from the battery and Tier-3 loads.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <Legend items={[{ label: "Baseline", color: "--series-baseline" }, { label: "GridSetu", color: "--series-gridsetu" },
          { label: "DISCOM cap", color: "--amber-fill", dash: true }, { label: "Baseline dark", color: "--danger/0.25", area: true }]} />
        {f && series && mask ? (
          <TimeChart ariaLabel="Feeder import" t0={f.t0} yLabel="kW" height={230} series={series}
            refLines={[{ y: f.capacity_kw, label: `Rating ${f.capacity_kw} kW` }]}
            shade={[{ mask, color: "--danger/0.14", label: "Baseline dark" }]} />
        ) : <Skeleton className="h-[230px]" />}
      </CardContent>
    </Card>
  );
}

function CurtailChart({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const series = useMemo(() => f && [
    { label: "Baseline unserved", values: f.variants.baseline.series.unserved, color: "--series-baseline", unit: "kW" },
    { label: "GridSetu unserved", values: f.variants[right].series.unserved, color: "--series-gridsetu", width: 2, unit: "kW" },
    { label: "Critical load unserved, baseline", values: f.variants.baseline.series.tier1_unserved, color: "--danger", unit: "kW" },
  ], [f, right]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Load not served</CardTitle>
          <CardDescription>Under GridSetu the unserved load is paused Tier-3 and Tier-2 appliances; under the baseline it is whole homes, the health centre included.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <Legend items={[{ label: "Baseline", color: "--series-baseline" }, { label: "GridSetu", color: "--series-gridsetu" },
          { label: "Critical load, baseline", color: "--danger" }]} />
        {f && series ? <TimeChart ariaLabel="Unserved load" t0={f.t0} yLabel="kW" height={230} series={series} />
          : <Skeleton className="h-[230px]" />}
      </CardContent>
    </Card>
  );
}

function SocChart({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const { data: meta } = useMeta();
  const floorPct = useMemo(() => {
    if (!f || !meta) return null;
    const b = meta.config.feeder.battery;
    const crit = Object.values(f.critical);
    let t1 = 0;
    for (let i = 0; i < f.n; i++) t1 = Math.max(t1, crit.reduce((a, c) => a + (c[i] ?? 0), 0));
    return (100 * (b.soc_min * b.energy_kwh + meta.config.feeder.tier1_island_hours * t1)) / b.energy_kwh;
  }, [f, meta]);
  const series = useMemo(() => f && [
    { label: "State of charge", values: f.variants[right].series.soc_pct, color: "--series-gridsetu", width: 2, unit: "%",
      fill: "--series-gridsetu/0.12" },
  ], [f, right]);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Community battery, 200 kWh</CardTitle>
          <CardDescription>The lowest band is never spent on anything except islanding the critical loads.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {f && series ? (
          <TimeChart ariaLabel="Battery state of charge" t0={f.t0} yLabel="%" height={200} yMin={0} yMax={100}
            series={series} refLines={floorPct ? [{ y: floorPct, label: "Critical-load island reserve" }] : undefined} />
        ) : <Skeleton className="h-[200px]" />}
      </CardContent>
    </Card>
  );
}

function ForecastChart() {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const { data: s } = useSummary();
  const series = useMemo(() => f && [
    { label: "q10", values: f.forecast.net.q10, color: "--series-gridsetu/0.35", width: 0.5, unit: "kW" },
    { label: "q90", values: f.forecast.net.q90, color: "--series-gridsetu/0.35", width: 0.5, unit: "kW" },
    { label: "q50 forecast", values: f.forecast.net.q50, color: "--series-gridsetu", width: 1.75, unit: "kW" },
    { label: "Actual", values: f.actual_net, color: "--foreground", width: 1, unit: "kW" },
  ], [f]);
  const sk = s?.forecast_skill.net_load;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Day-ahead forecast of feeder load</CardTitle>
          <CardDescription>
            Quantile regression with conformal calibration.{sk && <> The q10 to q90 band held the actual <span className="num">{f0(sk.coverage_q10_q90_pct)}%</span> of the time (target 80%), median error <span className="num">{f1(sk.mape_q50_pct)}%</span>.</>}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <Legend items={[{ label: "q10 to q90", color: "--series-gridsetu/0.25", area: true },
          { label: "q50 forecast", color: "--series-gridsetu" }, { label: "Actual", color: "--foreground" }]} />
        {f && series ? (
          <TimeChart ariaLabel="Quantile forecast versus actual" t0={f.t0} yLabel="kW" height={200}
            series={series} band={{ lower: 0, upper: 1, color: "--series-gridsetu/0.18" }} />
        ) : <Skeleton className="h-[200px]" />}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ Reliability Reserve
const STAGE_TEXT: Record<string, string> = {
  "T-24h": "Offered with the day-ahead plan",
  "T-1h": "Confirmed with a nowcast",
  "T-15min": "Dispatch-ready",
  "real-time": "Called during the window",
  "post-event": "Verified after the window",
};

function ReserveTimeline({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const [day, setDay] = useState(week === "stress" ? 3 : 1);
  const [ack, setAck] = useState<AdmsAck | null>(null);
  const qc = useQueryClient();
  const inbox = useQuery({ queryKey: ["adms-inbox"], queryFn: api.inbox, staleTime: 0, enabled: !IS_DEMO });
  const publish = useMutation({
    mutationFn: (r: Reserve) => api.publishReserve(r),
    onSuccess: (a) => { setAck(a); qc.invalidateQueries({ queryKey: ["adms-inbox"] }); },
  });
  const reserves = f?.variants[right].reserves ?? [];
  const dayItems = reserves.filter((r) => new Date(`${r.window_start}Z`).getUTCDay() === (day + 1) % 7);
  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle>Reliability Reserve, published to ADMS/DERMS</CardTitle>
          <CardDescription>What GridSetu tells the control room about the 17:30 to 19:30 window, five times over, as an IEC 61968-5 DER group forecast.</CardDescription>
        </div>
        <Segmented label="Day" size="sm" value={String(day)} onChange={(v) => setDay(Number(v))}
          options={DAYS.map((d, i) => ({ value: String(i), label: d }))} />
      </CardHeader>
      <CardContent className="space-y-4">
        {!f ? <Skeleton className="h-36" /> : (
          <ol className="grid gap-3 md:grid-cols-5">
            {dayItems.map((r, i) => (
              <li key={r.stage} className="relative rounded-lg border bg-background/40 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-muted-foreground"><span className="num">{i + 1}</span>. {r.stage}</span>
                  <Badge tone={r.confidence_pct >= 80 ? "teal" : r.confidence_pct >= 50 ? "amber" : "danger"}>
                    <span className="num">{f0(r.confidence_pct)}%</span>
                  </Badge>
                </div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="num text-[24px] leading-none">{f0(r.reserve_kw)}</span>
                  <span className="text-[12px] text-muted-foreground">kW for {r.duration_h} h</span>
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">{STAGE_TEXT[r.stage]}</p>
                <dl className="mt-2 space-y-0.5 text-[12px]">
                  <div className="flex justify-between"><dt className="text-muted-foreground">Battery</dt><dd className="num">{f0(r.battery_kw)} kW</dd></div>
                  <div className="flex justify-between"><dt className="text-muted-foreground">Tier 3 + Tier 2</dt><dd className="num">{f0(r.tier3_kw + r.tier2_kw)} kW</dd></div>
                  {r.delivered_kw != null && <div className="flex justify-between"><dt className="text-muted-foreground">Delivered</dt><dd className="num text-primary">{f0(r.delivered_kw)} kW</dd></div>}
                </dl>
                <Button size="sm" variant="outline" className="mt-3 w-full" disabled={publish.isPending}
                  onClick={() => publish.mutate(r)}>
                  <Icon name="send" />Publish to ADMS
                </Button>
              </li>
            ))}
          </ol>
        )}
        {inbox.data && inbox.data.items.length > 0 && (
          <div>
            <h4 className="mb-2 text-[13px] font-medium">Received by the mock ADMS</h4>
            <ul className="divide-y rounded-lg border text-[12.5px]">
              {inbox.data.items.slice(0, 5).map((a) => (
                <li key={a.mrid} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <Icon name={a.accepted ? "circle-check" : "info"} className={a.accepted ? "text-primary" : "text-amber"} />
                  <span className="num text-muted-foreground">{a.received_at}</span>
                  <span>{a.reserve.stage} for {a.reserve.window_start.slice(5, 16).replace("T", " ")}</span>
                  <span className="num ml-auto">{f0(a.dispatchable_kw)} kW dispatchable</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
      <Dialog open={!!ack} onOpenChange={(o) => !o && setAck(null)}>
        {ack && (
          <DialogContent title={ack.accepted ? "Published" : "Published as information only"} description={ack.reason}>
            <div className="grid grid-cols-2 gap-3 text-[13px]">
              <div><div className="text-muted-foreground">Dispatchable</div><div className="num text-[20px]">{f0(ack.dispatchable_kw)} kW</div></div>
              <div><div className="text-muted-foreground">Record id</div><div className="num truncate text-[12px]">{ack.mrid}</div></div>
            </div>
            <pre data-lenis-prevent className="num mt-4 max-h-64 overflow-auto rounded-md border bg-background/60 p-3 text-[11.5px] leading-relaxed">
              {JSON.stringify(ack.reserve, null, 2)}
            </pre>
          </DialogContent>
        )}
      </Dialog>
    </Card>
  );
}

function Comms({ right }: { right: Variant }) {
  const week = useUI((s) => s.week);
  const { data: f } = useFeeder(week);
  const rows = f?.variants[right].comms ?? [];
  const NAMES: Record<string, string> = {
    urllc_protection: "Protection (URLLC)", mmtc_ami: "Smart meters (mMTC)",
    control_2g4g: "Control, 2G/4G", embb_dashboard: "Dashboards (eMBB)",
  };
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Communication slices this week</CardTitle>
          <CardDescription>If a control message is still lost after its retries, the edge controller keeps critical loads on, holds the battery reserve and starts no new curtailment.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-[13px]">
          <thead className="text-left text-[12px] text-muted-foreground">
            <tr className="border-b">{["Slice", "Latency", "Packet loss", "Retries", "Messages", "Delivered"].map((h, i) => (
              <th key={h} className={cn("py-2 font-medium", i > 0 && "text-right")}>{h}</th>))}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.slice} className="border-b border-border/60">
                <td className="py-2">{NAMES[r.slice] ?? r.slice}</td>
                <td className="num text-right">{f0(r.latency_ms)} ms</td>
                <td className="num text-right">{f1(r.packet_loss * 100)}%</td>
                <td className="num text-right">{r.retries}</td>
                <td className="num text-right">{r.messages.toLocaleString("en-IN")}</td>
                <td className="num text-right">{f1(r.delivered_pct)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
