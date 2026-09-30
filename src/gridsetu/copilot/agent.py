"""Operator copilot: one agent loop, three interchangeable model providers.

  claude   Anthropic Messages API with tool use and streaming (needs ANTHROPIC_API_KEY)
  openai   any OpenAI-compatible chat API with tool calling: Groq, Gemini, OpenRouter, a
           local vLLM or LM Studio (GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY, or
           GRIDSETU_LLM_BASE_URL + GRIDSETU_LLM_API_KEY + GRIDSETU_LLM_MODEL)
  ollama   a local model through Ollama's /api/chat with tools (needs `ollama serve`)
  offline  no model: a rule-based router that calls the same tools and writes templated
           answers, so the copilot still works in a demo room with no internet

Choose with GRIDSETU_COPILOT=claude|openai|ollama|offline, or leave it on auto (claude if
its key is set, else an OpenAI-compatible key, else ollama if reachable, else offline).
Keys can live in a .env file in the project folder (see .env.example).

Every provider emits the same event stream, which the API forwards to the browser:
  {"type": "meta", "provider", "model"}   {"type": "text", "delta"}
  {"type": "tool_start", "id", "name", "label", "args"}   {"type": "tool_progress", "id", "message"}
  {"type": "tool_end", "id", "name", "ok", "error"?}      {"type": "ui", "action"}
  {"type": "done"}   {"type": "error", "message"}"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Callable

import httpx

from .offline import OfflineRouter
from .tools import TOOLS, TOOL_MAP, Context, call_tool

Emit = Callable[[dict], None]
MAX_ROUNDS = 8

SYSTEM = """You are the GridSetu operator copilot, inside a smart-grid control-room dashboard.

GridSetu is a forecast-uncertainty-aware, fairness-governed reliability layer for a low-income
peri-urban Indian feeder (F07: 420 homes, 35 micro-enterprises, a clinic, a school, a water pump,
street lights; 300 kW transformer; 200 kWh / 100 kW community battery). It publishes a Reliability
Reserve to Schneider EcoStruxure ADMS/DERMS. The simulated city "Setu Nagar" has three bid areas
(R1 North Industrial, R2 Central Urban, R3 South Peri-urban & Agri), coal, gas, hydro, a solar
park, wind and a national-grid import, six consumer classes with shedding priority (traction and
municipal never shed; irrigation and domestic first), a day-ahead market in 96 fifteen-minute
blocks and real-time redispatch. The stress week has a forced 125 MW coal outage (G1B) on
Thursday 18:00 and two overcast monsoon days.

How to work:
- Get every number from a tool. Never estimate or invent figures; if a tool cannot answer, say so.
- Prefer one or two well-chosen tool calls. get_moment and explain_price move the dashboard
  playhead, so the operator sees what you are describing.
- Answer like a senior control-room engineer: lead with the answer, then the evidence, in short
  paragraphs or a few bullets. Use units (MW, kW, kWh, ₹/kWh, Hz) and 24-hour times like Thu 18:00.
- All results are simulation on synthetic data. Say so once when you give headline figures, not
  in every sentence.
- Only call run_scenario when the operator asks to test a change; pass only the settings they
  named. It takes about a minute.
- When asked for a note or report for the DISCOM, write it formally: subject line, summary,
  what happened, what GridSetu did, figures, and next steps."""


def _context_block(ctx: Context) -> str:
    d = ctx.data()
    try:
        when = d.when(ctx.week, ctx.step)
    except Exception:
        when = f"step {ctx.step}"
    rec = ctx.get_record(ctx.run_id) if ctx.get_record else None
    return (f"Operator's dashboard right now: page {ctx.page}, "
            f"{'stress' if ctx.week == 'stress' else 'normal (representative)'} week, playhead at {when} "
            f"(step {ctx.step}), run '{getattr(rec, 'label', ctx.run_id)}' ({ctx.run_id}). "
            "'Now', 'here' or 'this moment' means the playhead.")


def _run_tool(ctx: Context, emit: Emit, name: str, args: dict) -> dict:
    tid = uuid.uuid4().hex[:8]
    tool = TOOL_MAP.get(name)
    emit({"type": "tool_start", "id": tid, "name": name, "args": args,
          "label": tool.label(args) if tool else name})
    ctx.progress = lambda m: emit({"type": "tool_progress", "id": tid, "message": m})
    ctx.ui.clear()
    result = call_tool(ctx, name, args)
    for a in ctx.ui:
        emit({"type": "ui", "action": a})
    ok = "error" not in result
    emit({"type": "tool_end", "id": tid, "name": name, "ok": ok, **({} if ok else {"error": result["error"]})})
    return result


def _dump(result: dict, limit: int = 12000) -> str:
    s = json.dumps(result, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + '..."(truncated)"'


# ------------------------------------------------------------------ Claude
class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str | None = None):
        import anthropic
        self.model = model or os.environ.get("GRIDSETU_MODEL", "claude-sonnet-5")
        kw = {}
        if os.environ.get("GRIDSETU_ANTHROPIC_BASE_URL"):
            kw["base_url"] = os.environ["GRIDSETU_ANTHROPIC_BASE_URL"]
        self.client = anthropic.Anthropic(**kw)
        self.tools = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in TOOLS]
        self.tools[-1] = {**self.tools[-1], "cache_control": {"type": "ephemeral"}}

    def run(self, ctx: Context, history: list[dict], emit: Emit):
        emit({"type": "meta", "provider": self.name, "model": self.model})
        system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}},
                  {"type": "text", "text": _context_block(ctx)}]
        msgs = [{"role": m["role"], "content": m["content"]} for m in history if m.get("content")]
        for _ in range(MAX_ROUNDS):
            with self.client.messages.stream(model=self.model, max_tokens=2000, system=system,
                                             tools=self.tools, messages=msgs) as stream:
                for ev in stream:
                    if ev.type == "text":
                        emit({"type": "text", "delta": ev.text})
                final = stream.get_final_message()
            msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in final.content]})
            uses = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason != "tool_use" or not uses:
                return
            results = []
            for b in uses:
                res = _run_tool(ctx, emit, b.name, dict(b.input or {}))
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": _dump(res),
                                **({"is_error": True} if "error" in res else {})})
            msgs.append({"role": "user", "content": results})
            emit({"type": "text", "delta": "\n\n"})
        emit({"type": "text", "delta": "\n\n(Stopped after several tool rounds. Ask a narrower question.)"})


# ------------------------------------------------------------------ Ollama
class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or os.environ.get("GRIDSETU_OLLAMA_MODEL", "qwen2.5:7b-instruct")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        self.tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                         "parameters": t.schema}} for t in TOOLS]

    @staticmethod
    def available(host: str | None = None) -> bool:
        h = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        if not h.startswith("http"):
            h = f"http://{h}"
        try:
            return httpx.get(f"{h}/api/tags", timeout=0.6).status_code == 200
        except Exception:
            return False

    def run(self, ctx: Context, history: list[dict], emit: Emit):
        emit({"type": "meta", "provider": self.name, "model": self.model})
        msgs = [{"role": "system", "content": SYSTEM + "\n\n" + _context_block(ctx)}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in history if m.get("content")]
        with httpx.Client(timeout=180) as http:
            for _ in range(MAX_ROUNDS):
                r = http.post(f"{self.host}/api/chat", json={"model": self.model, "messages": msgs,
                                                             "tools": self.tools, "stream": False,
                                                             "options": {"temperature": 0.2}})
                r.raise_for_status()
                msg = r.json().get("message", {})
                calls = msg.get("tool_calls") or []
                text = msg.get("content") or ""
                if text:
                    for chunk in re.findall(r"\S+\s*", text):   # word-by-word so the UI streams
                        emit({"type": "text", "delta": chunk})
                msgs.append({"role": "assistant", "content": text, **({"tool_calls": calls} if calls else {})})
                if not calls:
                    return
                for c in calls:
                    fn = c.get("function", {})
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    res = _run_tool(ctx, emit, fn.get("name", ""), args)
                    msgs.append({"role": "tool", "content": _dump(res, 8000)})
                emit({"type": "text", "delta": "\n\n"})


# ------------------------------------------------------------------ OpenAI-compatible
# (key variable, base URL, default model). Free tiers change their model line-ups often:
# override the model with GRIDSETU_LLM_MODEL if a default is retired.
OPENAI_PRESETS = [
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
]


def openai_config() -> dict | None:
    """Which OpenAI-compatible endpoint to use, from the environment, or None."""
    base = os.environ.get("GRIDSETU_LLM_BASE_URL")
    key = os.environ.get("GRIDSETU_LLM_API_KEY")
    model = os.environ.get("GRIDSETU_LLM_MODEL")
    if base:
        return {"base_url": base.rstrip("/"), "api_key": key or "not-needed", "model": model or "default",
                "source": "GRIDSETU_LLM_BASE_URL"}
    for var, url, default in OPENAI_PRESETS:
        if os.environ.get(var):
            return {"base_url": url, "api_key": os.environ[var], "model": model or default, "source": var}
    return None


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, cfg: dict | None = None, transport: httpx.BaseTransport | None = None):
        cfg = cfg or openai_config()
        if not cfg:
            raise RuntimeError("No OpenAI-compatible API key or GRIDSETU_LLM_BASE_URL is set")
        self.base, self.key, self.model, self.source = cfg["base_url"], cfg["api_key"], cfg["model"], cfg["source"]
        self.transport = transport
        self.tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                         "parameters": t.schema}} for t in TOOLS]

    def run(self, ctx: Context, history: list[dict], emit: Emit):
        emit({"type": "meta", "provider": self.name, "model": self.model})
        msgs: list[dict] = [{"role": "system", "content": SYSTEM + "\n\n" + _context_block(ctx)}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in history if m.get("content")]
        headers = {"Authorization": f"Bearer {self.key}", "HTTP-Referer": "https://github.com/HUNT-001/gridsetu",
                   "X-Title": "GridSetu copilot"}
        with httpx.Client(timeout=120, headers=headers, transport=self.transport) as http:
            for _ in range(MAX_ROUNDS):
                r = http.post(f"{self.base}/chat/completions", json={
                    "model": self.model, "messages": msgs, "tools": self.tools, "tool_choice": "auto",
                    "temperature": 0.2, "max_tokens": 1500})
                if r.status_code >= 400:
                    raise RuntimeError(f"{self.source} endpoint returned {r.status_code}: {r.text[:240]}")
                msg = (r.json().get("choices") or [{}])[0].get("message", {})
                calls = msg.get("tool_calls") or []
                text = msg.get("content") or ""
                if text:
                    for chunk in re.findall(r"\S+\s*", text):
                        emit({"type": "text", "delta": chunk})
                msgs.append({"role": "assistant", "content": text or None, **({"tool_calls": calls} if calls else {})})
                if not calls:
                    return
                for c in calls:
                    fn = c.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    res = _run_tool(ctx, emit, fn.get("name", ""), args if isinstance(args, dict) else {})
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": _dump(res, 8000)})
                emit({"type": "text", "delta": "\n\n"})
        emit({"type": "text", "delta": "\n\n(Stopped after several tool rounds. Ask a narrower question.)"})


# ------------------------------------------------------------------ offline
class OfflineProvider:
    name = "offline"
    model = "rule-based"

    def run(self, ctx: Context, history: list[dict], emit: Emit):
        emit({"type": "meta", "provider": self.name, "model": self.model})
        question = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        OfflineRouter(lambda n, a: _run_tool(ctx, emit, n, a), ctx).answer(question, emit)


def pick_provider(preference: str | None = None):
    pref = (preference or os.environ.get("GRIDSETU_COPILOT", "auto")).lower()
    if pref == "claude" or (pref == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        try:
            return ClaudeProvider()
        except Exception:
            if pref == "claude":
                raise
    if pref == "openai" or (pref == "auto" and openai_config()):
        try:
            return OpenAICompatProvider()
        except Exception:
            if pref == "openai":
                raise
    if pref == "ollama" or (pref == "auto" and OllamaProvider.available()):
        return OllamaProvider()
    return OfflineProvider()


def status() -> dict:
    pref = os.environ.get("GRIDSETU_COPILOT", "auto").lower()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    oa = openai_config()
    oll = OllamaProvider.available() if not (has_key or oa) or pref == "ollama" else False
    if pref == "claude" or (pref == "auto" and has_key):
        active, model = "claude", os.environ.get("GRIDSETU_MODEL", "claude-sonnet-5")
    elif pref == "openai" or (pref == "auto" and oa):
        active, model = "openai", (oa or {}).get("model", "unset")
    elif pref == "ollama" or (pref == "auto" and oll):
        active, model = "ollama", os.environ.get("GRIDSETU_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    else:
        active, model = "offline", "rule-based"
    return {"provider": active, "model": model, "preference": pref, "anthropic_key": has_key,
            "openai_compatible": (oa or {}).get("source"), "ollama": oll}


def run_turn(ctx: Context, history: list[dict], emit: Emit, provider=None):
    try:
        (provider or pick_provider()).run(ctx, history, emit)
        emit({"type": "done"})
    except Exception as e:  # surface model/network failures in the chat instead of hanging
        name = type(e).__name__
        hint = ""
        if "Authentication" in name or "401" in str(e):
            hint = " Check the API key in your .env file."
        elif "Connect" in name:
            hint = " The model endpoint is unreachable; set GRIDSETU_COPILOT=offline to use the offline assistant."
        emit({"type": "error", "message": f"{name}: {str(e)[:300]}.{hint}"})
