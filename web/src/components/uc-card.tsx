import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Legend, TimeChart } from "@/components/charts/time-chart";
import { useUc } from "@/lib/queries";
import { useStepInt, useUI } from "@/lib/store";
import { f0, f1 } from "@/lib/format";
import type { UcPayload } from "@/lib/types";

/** Indian money units: crore (10^7) for large sums, lakh (10^5) below that. */
const lakh = (inr: number) => (Math.abs(inr) >= 1e7 ? `₹${(inr / 1e7).toFixed(2)} cr` : `₹${f0(inr / 1e5)} lakh`);
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Merge a 0/1 series into [start, end) runs of 1s. */
function runs(on: boolean[]): [number, number][] {
  const out: [number, number][] = [];
  let s = -1;
  on.forEach((v, i) => {
    if (v && s < 0) s = i;
    if (!v && s >= 0) { out.push([s, i]); s = -1; }
  });
  if (s >= 0) out.push([s, on.length]);
  return out;
}

export function UcCard() {
  const week = useUI((s) => s.week);
  const uc = useUc(week);
  if (uc.metaLoaded && !uc.available) return null;
  const u = uc.data;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Unit commitment: which plants to run, not just how hard</CardTitle>
          <CardDescription className="max-w-[90ch]">
            A day-ahead mixed-integer schedule (PyPSA with HiGHS). Each plant can be off, but starting it costs money and it must then
            stay on for its minimum time. It is compared with the linear market used everywhere else, which keeps coal on and lets gas
            run at any output for free.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>{!u ? <Skeleton className="h-72" /> : <UcBody u={u} />}</CardContent>
    </Card>
  );
}

function UcBody({ u }: { u: UcPayload }) {
  const units = Object.keys(u.status);
  const lpOn = useMemo(() => Object.fromEntries(units.map((g) => [g, (u.gen_lp[g] ?? []).map((x) => (x ?? 0) > 0.1)])), [u, units]);
  const lpHours = Object.fromEntries(units.map((g) => [g, lpOn[g].filter(Boolean).length * u.dt_min / 60]));
  const extraShed = u.shed_uc_mwh - u.shed_lp_mwh;
  const dCost = u.cost_uc_inr.total - u.cost_lp_inr.total;
  const price = useMemo(() => [
    { label: "Linear market", values: u.price_lp.R3, color: "--series-baseline", unit: "₹/kWh" },
    { label: "With unit commitment", values: u.price_uc.R3, color: "--series-gridsetu", width: 2, unit: "₹/kWh" },
  ], [u]);
  return (
    <div className="space-y-5">
      <div className="grid gap-5 @[47rem]:grid-cols-[minmax(0,1fr)_340px]">
        <div>
          <h4 className="mb-2 text-[13px] font-medium">When each plant runs, day-ahead schedule</h4>
          <CommitStrips u={u} units={units} lpOn={lpOn} />
        </div>
        <div className="space-y-3">
          <p className="text-[13px] leading-relaxed">
            {extraShed > 0.5 ? (
              <>Start-up cost and minimum load make the gas unit too expensive for short evening spikes, so the schedule sheds{" "}
                <b className="num font-medium">{f0(extraShed)} MWh</b> more than the linear market and costs{" "}
                <b className="num font-medium">{lakh(dCost)}</b> more over the week. The linear market is optimistic about how cheaply peaks can be met.</>
            ) : (
              <>Committing units explicitly changes little this week: the schedule costs <b className="num font-medium">{lakh(Math.abs(dCost))}</b>{" "}
                {dCost >= 0 ? "more" : "less"} than the linear market.</>
            )}
          </p>
          <table className="w-full text-[12.5px]">
            <thead className="text-left text-muted-foreground">
              <tr className="border-b"><th className="py-1.5 font-medium">Week cost</th><th className="whitespace-nowrap text-right font-medium">Linear</th><th className="whitespace-nowrap pl-3 text-right font-medium">Commitment</th></tr>
            </thead>
            <tbody>
              {(["energy", "startup", "shed", "total"] as const).map((k) => (
                <tr key={k} className={k === "total" ? "font-medium" : "border-b border-border/60"}>
                  <td className="py-1.5">{{ energy: "Energy", startup: "Start-ups", shed: "Load shed, at value of lost load", total: "Total" }[k]}</td>
                  <td className="num text-right">{lakh(u.cost_lp_inr[k])}</td>
                  <td className="num text-right">{lakh(u.cost_uc_inr[k])}</td>
                </tr>
              ))}
              <tr className="border-t"><td className="py-1.5">Energy shed</td><td className="num text-right">{f0(u.shed_lp_mwh)} MWh</td><td className="num text-right">{f0(u.shed_uc_mwh)} MWh</td></tr>
            </tbody>
          </table>
          <table className="w-full text-[12.5px]">
            <thead className="text-left text-muted-foreground">
              <tr className="border-b"><th className="py-1.5 font-medium">Plant</th><th className="text-right font-medium">Starts</th><th className="text-right font-medium">Hours on</th><th className="text-right font-medium">Linear hours</th></tr>
            </thead>
            <tbody>
              {units.map((g) => (
                <tr key={g} className="border-b border-border/60">
                  <td className="py-1.5 font-medium">{g}</td>
                  <td className="num text-right">{u.startups[g] ?? 0}</td>
                  <td className="num text-right">{f1(u.hours_on[g])}</td>
                  <td className="num text-right">{f1(lpHours[g])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-[13px] font-medium">Day-ahead price in R3</h4>
          <Legend items={price.map((p) => ({ label: p.label, color: p.color }))} />
        </div>
        <TimeChart ariaLabel="R3 day-ahead price, linear market versus unit commitment" t0={u.t0} yLabel="₹/kWh"
          height={200} yMin={0} series={price} />
      </div>
      <p className="text-[12px] text-muted-foreground">{u.note} Feeder results on the other pages use the linear market so they stay comparable with Phase 1.</p>
    </div>
  );
}

function CommitStrips({ u, units, lpOn }: { u: UcPayload; units: string[]; lpOn: Record<string, boolean[]> }) {
  const step = useStepInt();
  const n = u.n;
  const W = 720, rowH = 14, gap = 6, labelW = 118;
  const rows = units.flatMap((g) => [
    { key: `${g}-uc`, label: `${g}`, sub: "commitment", on: u.status[g].map((x) => x > 0.5), color: "var(--series-gridsetu)" },
    { key: `${g}-lp`, label: "", sub: "linear", on: lpOn[g], color: "var(--series-baseline)" },
  ]);
  const H = rows.length * (rowH + gap) + 20;
  const x = (i: number) => labelW + (i / n) * (W - labelW);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
      aria-label={`On and off schedule per plant: ${units.map((g) => `${g} ${f1(u.hours_on[g])} hours on`).join(", ")}`}>
      {Array.from({ length: 8 }, (_, d) => (
        <g key={d}>
          <line x1={x(d * 96)} x2={x(d * 96)} y1={0} y2={H - 16} stroke="var(--grid)" />
          {d < 7 && <text x={x(d * 96) + 4} y={H - 4} fontSize={11} fill="var(--muted-foreground)">{DAYS[d]}</text>}
        </g>
      ))}
      {rows.map((r, i) => {
        const y = i * (rowH + gap) + (i % 2 ? -3 : 0);
        return (
          <g key={r.key}>
            {r.label && <text x={0} y={y + rowH - 2} fontSize={12} fontWeight={600} fill="var(--foreground)">{r.label}</text>}
            <text x={labelW - 8} y={y + rowH - 3} fontSize={10.5} textAnchor="end" fill="var(--muted-foreground)">{r.sub}</text>
            <rect x={labelW} y={y} width={W - labelW} height={rowH} rx={3} fill="var(--raised)" />
            {runs(r.on).map(([a, b]) => (
              <rect key={a} x={x(a)} y={y} width={Math.max(1, x(b) - x(a))} height={rowH} rx={2} fill={r.color} />
            ))}
          </g>
        );
      })}
      <line x1={x(step)} x2={x(step)} y1={0} y2={H - 16} stroke="var(--amber-fill)" strokeWidth={1.5} />
    </svg>
  );
}
