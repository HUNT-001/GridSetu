const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export const f0 = (x: number | null | undefined) => (x == null || Number.isNaN(x) ? "–" : nf0.format(x));
export const f1 = (x: number | null | undefined) => (x == null || Number.isNaN(x) ? "–" : nf1.format(x));
export const f2 = (x: number | null | undefined) => (x == null || Number.isNaN(x) ? "–" : nf2.format(x));
export const pct = (x: number | null | undefined, d = 0) =>
  x == null || Number.isNaN(x) ? "–" : `${x.toFixed(d)}%`;
export const change = (base: number, next: number) => {
  if (!base) return "n/a";
  const c = ((next - base) / base) * 100;
  return `${c > 0 ? "+" : c < 0 ? "−" : ""}${Math.abs(c).toFixed(0)}%`;
};

const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const HM = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });

/** The simulation clock is local Indian time stored naive; format it as-is (UTC formatter). */
export function stepDate(t0: string, dtMin: number, step: number): Date {
  const base = Date.parse(t0.endsWith("Z") ? t0 : `${t0}Z`);
  return new Date(base + Math.floor(step) * dtMin * 60_000);
}
export const fmtDay = (d: Date) => DAY.format(d);
export const fmtHM = (d: Date) => HM.format(d);
export const fmtStep = (t0: string, dtMin: number, step: number) => {
  const d = stepDate(t0, dtMin, step);
  return `${fmtDay(d)}, ${fmtHM(d)}`;
};
/** Fractional hour of day for a step (for sky colour, sun position). */
export const hourOf = (dtMin: number, step: number) => ((step * dtMin) / 60) % 24;

export const STATE_LABEL: Record<string, string> = {
  normal: "Normal",
  cap: "Meeting a DISCOM curtailment request",
  sps_relief: "Fast relief to the protection scheme",
  rotation_trip: "Tripped by rotational load shedding",
  sps_trip: "Tripped by the special protection scheme",
  cap_shortfall_trip: "Tripped: request larger than available relief",
  "cap_shortfall_trip+island": "Feeder tripped, critical loads islanded on the battery",
  "rotation_trip+island": "Feeder tripped, critical loads islanded on the battery",
  "sps_trip+island": "Feeder tripped, critical loads islanded on the battery",
  local_trip: "Transformer overload trip, waiting for the lineman",
  "local_trip+island": "Overload trip, critical loads islanded on the battery",
  overload_event: "Transformer overloaded and tripping",
};
export const isDark = (state: string) => state.includes("trip") && state !== "overload_event";
