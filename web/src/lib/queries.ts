import { keepPreviousData, QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { api, IS_DEMO } from "./api";
import { useUI } from "./store";
import type {
  CityPayload, FeederPayload, HouseholdsPayload, IslandPayload, Meta, NetworkPayload, RunRecord,
  Summary, WamsPayload, Week,
} from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // payload URLs are immutable (content-hash run ids): cache forever, never refetch
      staleTime: Infinity, gcTime: 30 * 60_000, retry: 1, refetchOnWindowFocus: false,
    },
  },
});

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    staleTime: 0,
    refetchInterval: (q) => (q.state.data?.runs.some((r) => r.status !== "ready" && r.status !== "failed")
      ? 1500 : false),
  });
}

/** The run the UI shows: the user's pick, else the reference run. */
export function useActiveRun(): { id: string | null; run: RunRecord | undefined; ready: boolean } {
  const { data } = useRuns();
  const picked = useUI((s) => s.runId);
  const id = picked ?? data?.reference ?? null;
  const run = data?.runs.find((r) => r.id === id);
  return { id, run, ready: run?.status === "ready" };
}

const WEEKLY = new Set(["city", "feeder", "households", "island", "network"]);
const key = (id: string | null, resource: string, week?: Week) =>
  ["res", id, resource, WEEKLY.has(resource) ? (resource === "network" ? "stress" : week) : null] as const;

function useResource<T>(resource: string, weekArg?: Week) {
  const { id, ready } = useActiveRun();
  const current = useUI((s) => s.week);
  const week = weekArg ?? current;
  return useQuery({
    queryKey: key(id, resource, week),
    queryFn: () => api.resource<T>(id!, resource, week),
    enabled: !!id && ready,
    placeholderData: keepPreviousData,   // switching runs keeps the old view until the new one lands
  });
}

export const useMeta = () => useResource<Meta>("meta");
export const useSummary = () => useResource<Summary>("summary");
export const useWams = () => useResource<WamsPayload>("wams");
export const useNetwork = () => useResource<NetworkPayload>("network");
export const useCity = (week?: Week) => useResource<CityPayload>("city", week);
export const useFeeder = (week?: Week) => useResource<FeederPayload>("feeder", week);
export const useHouseholds = (week?: Week) => useResource<HouseholdsPayload>("households", week);
export const useIsland = (week?: Week) => useResource<IslandPayload>("island", week);

/** Warm every payload of the active run while the browser is idle, current week first,
 *  so page and week switches are instant. */
export function usePrefetchRun() {
  const qc = useQueryClient();
  const { id, ready } = useActiveRun();
  const week = useUI((s) => s.week);
  useEffect(() => {
    if (!id || !ready) return;
    const other: Week = week === "stress" ? "representative" : "stress";
    const jobs: [string, Week | undefined][] = [
      ["meta", undefined], ["summary", undefined], ["city", week], ["feeder", week],
      ["households", week], ["wams", undefined], ["island", week], ["network", undefined],
      ["city", other], ["feeder", other], ["households", other], ["island", other],
    ];
    let cancelled = false;
    const idle = (cb: () => void) =>
      ("requestIdleCallback" in window ? window.requestIdleCallback(cb, { timeout: 800 }) : setTimeout(cb, 50));
    const run = (i: number) => {
      if (cancelled || i >= jobs.length) return;
      const [r, w] = jobs[i];
      qc.prefetchQuery({ queryKey: key(id, r, w), queryFn: () => api.resource(id, r, w) })
        .finally(() => idle(() => run(i + 1)));
    };
    idle(() => run(0));
    return () => { cancelled = true; };
  }, [id, ready, week, qc]);
}

// ------------------------------------------------------------ live run progress (SSE)
type Listener = () => void;
const progressState = new Map<string, RunRecord>();
const listeners = new Set<Listener>();
const sources = new Map<string, EventSource>();

function watch(id: string) {
  if (IS_DEMO || sources.has(id)) return;
  const es = new EventSource(api.progressUrl(id));
  es.onmessage = (e) => {
    const rec = JSON.parse(e.data) as RunRecord;
    progressState.set(id, rec);
    listeners.forEach((l) => l());
    if (rec.status === "ready" || rec.status === "failed") {
      es.close();
      sources.delete(id);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  };
  es.onerror = () => { es.close(); sources.delete(id); };
  sources.set(id, es);
}

export function useRunProgress(id: string | null): RunRecord | undefined {
  useEffect(() => { if (id) watch(id); }, [id]);
  return useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => (id ? progressState.get(id) : undefined),
  );
}
