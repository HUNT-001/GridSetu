import type { LabKnobs, Reserve, RunRecord } from "./types";

export const IS_DEMO = import.meta.env.MODE === "demo";
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) { super(message); }
}

// ------------------------------------------------------------ demo snapshot (static build)
type Snapshot = { runs: { reference: string; runs: RunRecord[] }; payloads: Record<string, unknown>;
  defaults: LabKnobs };
let snapshot: Promise<Snapshot> | null = null;
const snapModules = import.meta.glob<{ default: Snapshot }>("../snapshot.gen.json");
function loadSnapshot(): Promise<Snapshot> {
  if (!snapshot) {
    const loader = snapModules["../snapshot.gen.json"];
    if (!loader) throw new ApiError(500, "This build has no bundled data snapshot");
    snapshot = loader().then((m) => m.default);
  }
  return snapshot;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, init);
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail)
      : `Request failed with ${res.status}`;
    throw new ApiError(res.status, msg, body);
  }
  return body as T;
}

export const api = {
  async runs(): Promise<{ reference: string; runs: RunRecord[] }> {
    if (IS_DEMO) return (await loadSnapshot()).runs;
    return http("/runs");
  },
  async resource<T>(runId: string, resource: string, week?: string): Promise<T> {
    if (IS_DEMO) {
      const key = week && resource !== "meta" && resource !== "summary" && resource !== "wams"
        ? `${resource}:${resource === "network" ? "stress" : week}` : resource;
      const p = (await loadSnapshot()).payloads[key];
      if (!p) throw new ApiError(404, `${key} is not in the snapshot`);
      return p as T;
    }
    return http(`/runs/${runId}/${resource}${week ? `?week=${week}` : ""}`);
  },
  async defaults(): Promise<LabKnobs> {
    if (IS_DEMO) return (await loadSnapshot()).defaults;
    return http("/lab/defaults");
  },
  async startRun(knobs: Partial<LabKnobs>, label: string): Promise<RunRecord> {
    if (IS_DEMO) throw new ApiError(400, "Scenario runs need the GridSetu API. Start it with `gridsetu serve`.");
    return http("/runs", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ knobs, label }) });
  },
  async publishReserve(r: Reserve): Promise<AdmsAck> {
    if (IS_DEMO) {
      const accepted = r.confidence_pct >= 50 && r.reserve_kw > 0;
      return { mrid: crypto.randomUUID(), received_at: new Date().toISOString().slice(0, 19), accepted,
        reason: accepted ? "Registered as dispatchable DER group (demo, not sent)" : "Confidence below 50 %: held as information only",
        dispatchable_kw: accepted ? Math.round(r.reserve_kw * r.confidence_pct) / 100 : 0, reserve: r };
    }
    return http("/adms/ingest", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(r) });
  },
  async inbox(): Promise<{ items: AdmsAck[] }> {
    if (IS_DEMO) return { items: [] };
    return http("/adms/inbox");
  },
  progressUrl: (id: string) => `${BASE}/api/v1/runs/${id}/progress`,
};

export interface AdmsAck {
  mrid: string; received_at: string; accepted: boolean; reason: string; dispatchable_kw: number; reserve: Reserve;
}
