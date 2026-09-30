// Pulls every payload of the reference run from a running API into src/snapshot.gen.json,
// so `npm run build:demo` can produce one self-contained HTML file with no server.
import { writeFileSync } from "node:fs";
const API = process.env.GRIDSETU_API ?? "http://127.0.0.1:8000/api/v1";
const get = async (p) => { const r = await fetch(`${API}${p}`); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };
const runs = await get("/runs");
const id = runs.reference;
const ref = runs.runs.find((r) => r.id === id);
if (!ref || ref.status !== "ready") throw new Error("Reference run is not ready yet; wait for `gridsetu serve` to finish it.");
const payloads = {};
for (const r of ["meta", "summary", "wams"]) payloads[r] = await get(`/runs/${id}/${r}`);
for (const w of ["stress", "representative"])
  for (const r of ["city", "feeder", "households", "island"]) payloads[`${r}:${w}`] = await get(`/runs/${id}/${r}?week=${w}`);
payloads["network:stress"] = await get(`/runs/${id}/network`);
for (const study of payloads.meta.studies ?? []) {          // Phase 2: fleet, uc, map
  if (study === "map") payloads.map = await get(`/runs/${id}/map`);
  else for (const w of ["stress", "representative"]) payloads[`${study}:${w}`] = await get(`/runs/${id}/${study}?week=${w}`);
}
const defaults = await get("/lab/defaults");
const out = JSON.stringify({ runs: { reference: id, runs: [ref] }, payloads, defaults });
writeFileSync(new URL("../src/snapshot.gen.json", import.meta.url), out);
console.log(`snapshot: ${(out.length / 1e6).toFixed(1)} MB from run ${id}`);
