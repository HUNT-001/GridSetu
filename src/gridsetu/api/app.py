"""GridSetu API (FastAPI).

Routes (all under /api/v1):
  GET  /health
  GET  /runs                          list runs and their status
  POST /runs                          start a scenario-lab run  {"knobs": {...}, "label": "..."}
  GET  /runs/{id}                     status of one run
  GET  /runs/{id}/progress            Server-Sent Events: live progress of a running job
  GET  /runs/{id}/{resource}?week=    immutable, pre-gzipped JSON payload
  GET  /lab/defaults                  editable scenario knobs with current values
  POST /adms/ingest                   mock EcoStruxure ADMS/DERMS ingest of a Reliability Reserve
  GET  /adms/inbox                    what the mock ADMS has received

Payload URLs contain a content-hash run id, so they are served with
Cache-Control: immutable and a strong ETag: the browser fetches each one exactly once."""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import ENGINE_VERSION, compute_run, knobs_to_overrides, load_scenario_defaults, run_id_for

from ..envfile import load_env  # noqa: E402

load_env()   # API keys and settings from .env, before anything reads the environment

ROOT = Path(__file__).resolve().parents[3]
CACHE = Path(os.environ.get("GRIDSETU_CACHE", ROOT / ".cache" / "runs"))
WEB_DIST = Path(os.environ.get("GRIDSETU_WEB", ROOT / "web" / "dist"))
RESOURCES = {"meta", "summary", "wams", "city", "feeder", "households", "island", "network", "fleet", "uc", "map"}
WEEKLY = {"city", "feeder", "households", "island", "network", "fleet", "uc"}
DEFAULT_SEEDS = int(os.environ.get("GRIDSETU_SEEDS", "3"))


@dataclass
class RunRecord:
    id: str
    label: str
    seeds: int
    overrides: dict
    knobs: dict = field(default_factory=dict)
    status: str = "queued"          # queued | running | ready | failed
    progress: float = 0.0
    message: str = "Waiting to start"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    version: int = 0

    def public(self) -> dict:
        d = asdict(self)
        d.pop("version")
        return d


class RunStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs: dict[str, RunRecord] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sim")
        self.mem: OrderedDict[tuple, bytes] = OrderedDict()
        self._scan()

    def _scan(self):
        for d in self.root.glob("*/run.json"):
            try:
                rec = RunRecord(**json.loads(d.read_text()))
                if rec.status == "ready" and (d.parent / "meta.json.gz").exists():
                    self.runs[rec.id] = rec
            except Exception:
                continue

    def submit(self, overrides: dict, label: str, seeds: int, knobs: dict | None = None) -> RunRecord:
        rid = run_id_for(overrides, seeds)
        with self.lock:
            rec = self.runs.get(rid)
            if rec and rec.status in ("queued", "running", "ready"):
                return rec
            rec = RunRecord(rid, label, seeds, overrides, knobs or {})
            self.runs[rid] = rec
        self.pool.submit(self._execute, rec)
        return rec

    def _update(self, rec: RunRecord, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(rec, k, v)
            rec.version += 1

    def _execute(self, rec: RunRecord):
        self._update(rec, status="running", message="Starting", progress=0.01)
        try:
            payloads = compute_run(rec.overrides, rec.label, rec.seeds,
                                   lambda m, p: self._update(rec, message=m, progress=round(p, 3)),
                                   pf_every=2 if rec.seeds > 1 else 4)
            d = self.root / rec.id
            d.mkdir(parents=True, exist_ok=True)
            for key, blob in payloads.items():
                (d / f"{key.replace(':', '__')}.json.gz").write_bytes(blob)
            self._update(rec, status="ready", progress=1.0, message="Ready", finished_at=time.time())
            (d / "run.json").write_text(json.dumps(rec.public() | {"version": 0}))
        except Exception as e:  # surface the failure to the UI instead of hanging
            traceback.print_exc()
            self._update(rec, status="failed", message="Run failed", error=f"{type(e).__name__}: {e}")

    def payload(self, rid: str, key: str) -> bytes | None:
        mk = (rid, key)
        if mk in self.mem:
            self.mem.move_to_end(mk)
            return self.mem[mk]
        f = self.root / rid / f"{key.replace(':', '__')}.json.gz"
        if not f.exists():
            return None
        blob = f.read_bytes()
        self.mem[mk] = blob
        if len(self.mem) > 64:
            self.mem.popitem(last=False)
        return blob


store = RunStore(CACHE)
REFERENCE_ID = run_id_for({}, DEFAULT_SEEDS)
# Lab runs use one seed, so they are compared against a one-seed reference (same weather and
# load draws); otherwise seed-to-seed noise would show up as a scenario effect.
LAB_REFERENCE_ID = run_id_for({}, 1)
adms_inbox: list[dict] = []

app = FastAPI(title="GridSetu API", version=ENGINE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["ETag"])


def j(data, status=200, headers=None) -> Response:
    body = orjson.dumps(data)
    h = {"Cache-Control": "no-store", **(headers or {})}
    return Response(body, status_code=status, media_type="application/json", headers=h)


@app.on_event("startup")
def _startup():
    store.submit({}, "Reference scenario", DEFAULT_SEEDS)
    if LAB_REFERENCE_ID != REFERENCE_ID:
        store.submit({}, "Reference, 1 seed (lab baseline)", 1)


@app.get("/api/v1/health")
def health():
    return j({"ok": True, "engine": ENGINE_VERSION, "reference_run": REFERENCE_ID,
              "runs": len(store.runs)})


@app.get("/api/v1/runs")
def list_runs():
    runs = sorted(store.runs.values(), key=lambda r: r.created_at)
    return j({"reference": REFERENCE_ID, "lab_reference": LAB_REFERENCE_ID, "runs": [r.public() for r in runs]})


class LabRequest(BaseModel):
    knobs: dict = Field(default_factory=dict)
    label: str = "Lab scenario"


@app.post("/api/v1/runs", status_code=202)
def create_run(req: LabRequest):
    overrides = knobs_to_overrides(req.knobs)
    rec = store.submit(overrides, req.label[:60] or "Lab scenario", seeds=1, knobs=req.knobs)
    return j(rec.public(), status=202)


@app.get("/api/v1/runs/{rid}")
def get_run(rid: str):
    rec = store.runs.get(rid)
    if not rec:
        raise HTTPException(404, f"No run with id {rid}")
    return j(rec.public())


@app.get("/api/v1/runs/{rid}/progress")
async def run_progress(rid: str, request: Request):
    rec = store.runs.get(rid)
    if not rec:
        raise HTTPException(404, f"No run with id {rid}")

    async def gen():
        seen = -1
        while True:
            if await request.is_disconnected():
                return
            if rec.version != seen:
                seen = rec.version
                yield f"data: {orjson.dumps(rec.public()).decode()}\n\n"
            if rec.status in ("ready", "failed"):
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/v1/runs/{rid}/{resource}")
def get_payload(rid: str, resource: str, request: Request, week: str = "stress"):
    if resource not in RESOURCES:
        raise HTTPException(404, f"Unknown resource {resource}")
    rec = store.runs.get(rid)
    if not rec:
        raise HTTPException(404, f"No run with id {rid}")
    if rec.status != "ready":
        return j({"status": rec.status, "progress": rec.progress, "message": rec.message}, status=409)
    if resource == "network":
        week = "stress"
    key = f"{resource}:{week}" if resource in WEEKLY else resource
    blob = store.payload(rid, key)
    if blob is None:
        raise HTTPException(404, f"{key} is not available for run {rid}")
    etag = f'"{rid}-{key}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable",
               "Vary": "Accept-Encoding"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(blob, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(gzip.decompress(blob), media_type="application/json", headers=headers)


@app.get("/api/v1/lab/defaults")
def lab_defaults():
    return j(load_scenario_defaults())


class ReserveIn(BaseModel):
    feeder_id: str
    stage: str
    issued_at: str
    window_start: str
    window_end: str
    reserve_kw: float = Field(ge=0)
    energy_kwh: float = Field(ge=0)
    duration_h: float = Field(gt=0)
    confidence_pct: float = Field(ge=0, le=100)
    cost_inr_kwh: float = Field(ge=0)
    battery_kw: float = 0
    tier3_kw: float = 0
    tier2_kw: float = 0
    delivered_kw: float | None = None
    cim_profile: str = "IEC 61968-5 DERGroupForecast"


@app.post("/api/v1/adms/ingest")
def adms_ingest(r: ReserveIn):
    accepted = r.confidence_pct >= 50 and r.reserve_kw > 0
    ack = {
        "mrid": str(uuid.uuid4()),
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "accepted": accepted,
        "reason": "Registered as dispatchable DER group" if accepted
        else "Confidence below 50 %: held as information only",
        "dispatchable_kw": round(r.reserve_kw * r.confidence_pct / 100, 1) if accepted else 0.0,
        "reserve": r.model_dump(),
    }
    adms_inbox.insert(0, ack)
    del adms_inbox[50:]
    return j(ack, status=201)


@app.get("/api/v1/adms/inbox")
def adms_list():
    return j({"items": adms_inbox})


# ---------------------------------------------------------------- operator copilot
from ..copilot import agent as copilot_agent  # noqa: E402
from ..copilot.data import RunData  # noqa: E402
from ..copilot.live import MqttBridge, stream as live_stream  # noqa: E402
from ..copilot.tools import Context as CopilotContext  # noqa: E402

_rundata: dict[str, RunData] = {}


def open_run(rid: str) -> RunData:
    rec = store.runs.get(rid)
    if not rec or rec.status != "ready":
        raise KeyError(f"Run {rid} is not available or not finished")
    if rid not in _rundata:
        _rundata[rid] = RunData(rid, lambda key, r=rid: store.payload(r, key))
    return _rundata[rid]


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=8000)


class ChatContext(BaseModel):
    run_id: str | None = None
    week: str = Field(default="stress", pattern="^(stress|representative)$")
    step: int = Field(default=0, ge=0, le=100000)
    page: str = "/"


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    context: ChatContext = Field(default_factory=ChatContext)
    provider: str | None = Field(default=None, pattern="^(auto|claude|openai|ollama|offline)$")


@app.get("/api/v1/copilot/status")
def copilot_status():
    return j(copilot_agent.status())


@app.post("/api/v1/copilot/chat")
async def copilot_chat(req: ChatRequest, request: Request):
    rid = req.context.run_id or REFERENCE_ID
    rec = store.runs.get(rid)
    if not rec or rec.status != "ready":
        raise HTTPException(409, "That run is not ready yet")
    ctx = CopilotContext(
        run_id=rid, reference_id=REFERENCE_ID, lab_reference_id=LAB_REFERENCE_ID, week=req.context.week,
        step=min(req.context.step, 671), page=req.context.page, open_run=open_run,
        submit_run=lambda ov, label, knobs: store.submit(ov, label, seeds=1, knobs=knobs),
        get_record=lambda r: store.runs.get(r), list_records=lambda: sorted(store.runs.values(), key=lambda x: x.created_at),
    )
    history = [m.model_dump() for m in req.messages][-20:]
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    emit = lambda ev: loop.call_soon_threadsafe(queue.put_nowait, ev)  # noqa: E731
    provider = copilot_agent.pick_provider(req.provider) if req.provider else None
    fut = loop.run_in_executor(None, copilot_agent.run_turn, ctx, history, emit, provider)

    async def gen():
        while True:
            if await request.is_disconnected():
                return
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {orjson.dumps(ev).decode()}\n\n"
            if ev["type"] in ("done", "error"):
                await fut
                return

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/v1/live/stream")
async def live(request: Request, run: str | None = None, week: str = "stress", start: int = 0,
               speed: float = 4.0):
    rid = run or REFERENCE_ID
    d = open_run(rid)
    if week not in ("stress", "representative"):
        raise HTTPException(400, "week must be stress or representative")
    speed = max(0.25, min(speed, 48.0))
    broker = os.environ.get("GRIDSETU_MQTT")
    bridge = None
    if broker:
        try:
            bridge = MqttBridge(broker, rid)
        except Exception:
            bridge = None
    loop = asyncio.get_running_loop()
    it = live_stream(d, week, start, speed)

    async def gen():
        try:
            yield f"data: {orjson.dumps({'type': 'hello', 'run': rid, 'week': week, 'speed': speed, 'mqtt': bool(bridge)}).decode()}\n\n"
            while not await request.is_disconnected():
                step, msgs = await loop.run_in_executor(None, next, it)
                if bridge:
                    bridge.publish(msgs)
                yield f"data: {orjson.dumps({'type': 'tick', 'step': step, 'messages': [{'topic': t, 'payload': p} for t, p in msgs]}).decode()}\n\n"
        finally:
            if bridge:
                bridge.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- built front end (optional)
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
