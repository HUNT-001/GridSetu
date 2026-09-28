import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Legend, TimeChart } from "@/components/charts/time-chart";
import { useWams } from "@/lib/queries";
import { f1, f2 } from "@/lib/format";

const CASES = {
  A: { title: "Coal unit G1B trips while connected", text: "The rest of India holds frequency, so the national tie picks up the lost 125 MW and overloads. The special protection scheme sheds feeder blocks to bring it back under its thermal limit." },
  B: { title: "The national tie trips and the city islands", text: "The city loses its import in an instant. Under-frequency relays shed load in stages until generation and demand balance again." },
};

export default function WamsPage() {
  const { data: w } = useWams();
  const [c, setC] = useState<"A" | "B">("A");
  const runs = w?.runs;
  const b = runs?.[`${c}_baseline`], g = runs?.[`${c}_gridsetu`];
  const freq = useMemo(() => b && g && [
    { label: "City, baseline", values: b.f_city, color: "--series-baseline", unit: "Hz" },
    { label: "City, GridSetu", values: g.f_city, color: "--series-gridsetu", width: 2, unit: "Hz" },
    ...(c === "A" ? [{ label: "Rest of India", values: b.f_nat, color: "--foreground", width: 1, dash: [4, 3], unit: "Hz" }] : []),
  ], [b, g, c]);
  const power = useMemo(() => b && g && (c === "A" ? [
    { label: "Tie import, baseline", values: b.tie, color: "--series-baseline", unit: "MW" },
    { label: "Tie import, GridSetu", values: g.tie, color: "--series-gridsetu", width: 2, unit: "MW" },
  ] : [
    { label: "Load shed, baseline", values: b.shed, color: "--series-baseline", unit: "MW" },
    { label: "Load shed, GridSetu", values: g.shed, color: "--series-gridsetu", width: 2, unit: "MW" },
    { label: "GridSetu fast response", values: g.ffr, color: "--amber-fill", unit: "MW" },
  ]), [b, g, c]);

  if (!w) return <Skeleton className="h-[560px]" />;
  if (!b || !g) {
    return (
      <Card><CardContent className="py-10 text-center text-[13.5px] text-muted-foreground">
        This run has no forced outage, so there is no frequency event to study. Switch to the reference run or enable the outage in the scenario lab.
      </CardContent></Card>
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[72ch] text-[13.5px] leading-relaxed text-muted-foreground">
          Phasor measurement units report 50 frames a second. This study replays the first minute after the
          forced outage at {w.timestamp?.slice(11, 16)} on Thursday, with and without the fast response of GridSetu
          feeders ({f1(w.fleet_ffr_mw)} MW across 25% of the peri-urban feeders).
        </p>
        <Segmented<"A" | "B"> label="Event" value={c} onChange={setC} options={[
          { value: "A", label: "Generator trip" }, { value: "B", label: "Islanding" }]} />
      </div>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{CASES[c].title}</CardTitle>
            <CardDescription className="max-w-[80ch]">{CASES[c].text}</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-2">
          <div className="space-y-2">
            <Legend items={freq!.map((s) => ({ label: s.label, color: s.color, dash: !!s.dash }))} />
            <TimeChart ariaLabel="Frequency after the event" xKind="seconds" x={b.t} yLabel="Hz" height={240}
              yMin={c === "A" ? 49.6 : 48.9} yMax={50.4} valueFormat={(v) => v.toFixed(3)} series={freq!}
              refLines={c === "B" ? [{ y: 49.4, label: "UFLS stage 1" }, { y: 49.2, label: "UFLS stage 2" }] : undefined} />
          </div>
          <div className="space-y-2">
            <Legend items={power!.map((s) => ({ label: s.label, color: s.color }))} />
            <TimeChart ariaLabel="Tie flow or load shed after the event" xKind="seconds" x={b.t} yLabel="MW" height={240}
              series={power!} refLines={c === "A" ? [{ y: 150, label: "Tie thermal limit" }] : undefined} />
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {[b, g].map((r) => {
          const s = r.summary;
          return (
            <Card key={s.variant}>
              <CardHeader>
                <CardTitle>{s.variant === "baseline" ? "Baseline" : "With GridSetu fast response"}</CardTitle>
                <Badge tone={s.pilot_feeder_tripped ? "danger" : "teal"}>
                  {s.pilot_feeder_tripped ? "Pilot feeder tripped" : "Pilot feeder stayed on"}
                </Badge>
              </CardHeader>
              <CardContent className="space-y-3">
                <dl className="grid grid-cols-3 gap-3 text-[13px]">
                  {[["Nadir", `${f2(s.nadir_hz)} Hz`], ["RoCoF, 500 ms", `${f2(s.rocof_500ms_hz_s)} Hz/s`],
                    ["Settles at", `${f2(s.settling_hz)} Hz`], ["Load shed", `${f1(s.load_shed_mw)} MW`],
                    ["Peak tie import", s.peak_tie_import_mw == null ? "Islanded" : `${f1(s.peak_tie_import_mw)} MW`],
                    ["Inertia", `${f2(s.inertia_h_equiv_s)} s`]].map(([k, v]) => (
                    <div key={k}><dt className="text-[12px] text-muted-foreground">{k}</dt><dd className="num">{v}</dd></div>
                  ))}
                </dl>
                <ol className="space-y-1 border-t pt-3 text-[12.5px]">
                  {s.events.map((e) => (
                    <li key={e.event} className="flex justify-between gap-3">
                      <span><span className="num text-muted-foreground">{e.t_s.toFixed(2)} s</span> {e.event}</span>
                      <span className="num">{f1(e.mw)} MW</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
