"""Copilot tools, providers and live replay, against a real one-seed run."""
import json
import types

import pytest

from gridsetu.api.engine import compute_run
from gridsetu.copilot import agent
from gridsetu.copilot.data import RunData
from gridsetu.copilot.live import messages_at
from gridsetu.copilot.tools import Context, call_tool


@pytest.fixture(scope="session")
def run():
    blobs = compute_run({}, "test", 1, lambda m, p: None, pf_every=8)
    return RunData("test", blobs.get)


@pytest.fixture()
def ctx(run):
    rec = types.SimpleNamespace(id="test", label="Test run", status="ready", seeds=1, knobs={})
    return Context(run_id="test", reference_id="test", week="stress", step=360, open_run=lambda r: run,
                   get_record=lambda r: rec, list_records=lambda: [rec])


@pytest.mark.parametrize("text,step", [("Thu 18:00", 360), ("thursday 6pm", 360), ("step 12", 12),
                                        ("2026-09-17 18:00", 360), ("fri 7:30 pm", 4 * 96 + 78), (5, 5)])
def test_parse_time(run, text, step):
    assert run.parse_time(text, "stress") == step


def test_parse_time_rejects_nonsense(run):
    with pytest.raises(ValueError):
        run.parse_time("banana", "stress")


def test_get_moment_matches_payload_and_moves_playhead(ctx, run):
    r = call_tool(ctx, "get_moment", {"time": "Thu 18:30"})
    city = run.city("stress")["scenarios"]["baseline"]
    assert r["city"]["exchange_price_inr_kwh"] == city["exchange_price"][362]
    assert r["pilot_feeder"]["gridsetu"]["soc_pct"] == run.feeder("stress")["variants"]["gridsetu"]["series"]["soc_pct"][362]
    assert {"type": "seek", "week": "stress", "step": 362} in ctx.ui


def test_explain_price_at_the_outage_mentions_scarcity(ctx):
    r = call_tool(ctx, "explain_price", {"time": "Thu 18:30"})
    assert r["price_rt_inr_kwh"] >= 9.99
    assert any("ceiling" in x for x in r["reasons"])


def test_tools_return_errors_not_exceptions(ctx):
    assert "error" in call_tool(ctx, "get_household", {"household_id": "HH-999"})
    assert "error" in call_tool(ctx, "get_moment", {"time": "banana"})
    assert "error" in call_tool(ctx, "no_such_tool", {})
    ctx.submit_run = lambda *a: pytest.fail("must not submit")
    assert "error" in call_tool(ctx, "run_scenario", {})
    assert "error" in call_tool(ctx, "run_scenario", {"battery_kwh": -5})


def _collect(ctx, q, provider):
    ev = []
    agent.run_turn(ctx, [{"role": "user", "content": q}], ev.append, provider=provider)
    return ev, "".join(e.get("delta", "") for e in ev if e["type"] == "text")


@pytest.mark.parametrize("q,expect", [
    ("what is happening now?", "Pilot feeder, GridSetu"),
    ("why is the price high at Thu 18:30?", "ceiling"),
    ("how did gridsetu do?", "| Metric |"),
    ("show me HH-042", "HH-042"),
    ("reliability reserve for thursday", "T-24h"),
    ("draft a note for the DISCOM about thursday evening", "Subject"),
])
def test_offline_answers(ctx, q, expect):
    ev, text = _collect(ctx, q, agent.OfflineProvider())
    assert ev[-1]["type"] == "done"
    assert expect in text


def test_claude_tool_loop_builds_valid_messages(ctx):
    from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
    mk = lambda content, stop: Message(id="m", type="message", role="assistant", model="x", content=content,  # noqa: E731
                                       stop_reason=stop, stop_sequence=None, usage=Usage(input_tokens=1, output_tokens=1))
    script = [mk([ToolUseBlock(type="tool_use", id="t1", name="get_moment", input={"time": "Thu 18:00"})], "tool_use"),
              mk([TextBlock(type="text", text="Done.")], "end_turn")]
    calls = []

    class S:
        def __init__(self, m): self.m = m
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self):
            for b in self.m.content:
                if b.type == "text":
                    yield types.SimpleNamespace(type="text", text=b.text)
        def get_final_message(self): return self.m

    class M:
        def stream(self, **kw):
            calls.append(json.loads(json.dumps(kw, default=str)))
            return S(script[len(calls) - 1])

    p = agent.ClaudeProvider.__new__(agent.ClaudeProvider)
    p.model, p.client = "x", types.SimpleNamespace(messages=M())
    p.tools = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in agent.TOOLS]
    ev, text = _collect(ctx, "what happened at the outage?", p)
    assert text.strip() == "Done."
    second = calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[2]["content"][0]["type"] == "tool_result" and second[2]["content"][0]["tool_use_id"] == "t1"
    assert any(e["type"] == "ui" for e in ev)


def test_live_messages_cover_all_topics(run):
    topics = {t for t, _ in messages_at(run, "stress", 360)}
    assert {"city/state", "feeder/F07/scada", "feeder/F07/ami"} <= topics


# ---------------------------------------------------------------- OpenAI-compatible provider, .env
def test_openai_compatible_provider_runs_a_tool_loop(ctx):
    import httpx
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["authorization"] == "Bearer test-key"
        assert {t["function"]["name"] for t in body["tools"]} >= {"get_overview"}
        if len(calls) == 1:   # first round: the model asks for a tool
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "get_overview", "arguments": "{}"}}]}}]})
        tool_msg = body["messages"][-1]
        assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant",
                                                                  "content": "Critical loads stayed on."}}]})

    p = agent.OpenAICompatProvider({"base_url": "https://llm.test/v1", "api_key": "test-key",
                                    "model": "test-model", "source": "GROQ_API_KEY"},
                                   transport=httpx.MockTransport(handler))
    events = []
    agent.run_turn(ctx, [{"role": "user", "content": "How did the week go?"}], events.append, p)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "meta" and events[0]["provider"] == "openai"
    assert "tool_start" in kinds and "tool_end" in kinds and kinds[-1] == "done"
    assert "".join(e.get("delta", "") for e in events).strip().endswith("Critical loads stayed on.")
    assert len(calls) == 2


def test_openai_config_presets(monkeypatch):
    for var in ("GRIDSETU_LLM_BASE_URL", "GRIDSETU_LLM_API_KEY", "GRIDSETU_LLM_MODEL", "GROQ_API_KEY",
                "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert agent.openai_config() is None
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    cfg = agent.openai_config()
    assert cfg["source"] == "GEMINI_API_KEY" and "generativelanguage" in cfg["base_url"]
    monkeypatch.setenv("GRIDSETU_LLM_BASE_URL", "http://127.0.0.1:1234/v1/")
    monkeypatch.setenv("GRIDSETU_LLM_MODEL", "local")
    cfg = agent.openai_config()
    assert cfg["base_url"] == "http://127.0.0.1:1234/v1" and cfg["model"] == "local"


def test_env_file_loader(tmp_path, monkeypatch):
    from gridsetu.envfile import load_env
    f = tmp_path / ".env"
    f.write_text('# comment\nexport GS_A=1\nGS_B="two words"\nGS_C=x # trailing\nGS_KEEP=file\n\nnot a line\n')
    monkeypatch.setenv("GS_KEEP", "env")
    for k in ("GS_A", "GS_B", "GS_C"):
        monkeypatch.delenv(k, raising=False)
    loaded = load_env([f])
    import os
    assert os.environ["GS_A"] == "1" and os.environ["GS_B"] == "two words" and os.environ["GS_C"] == "x"
    assert os.environ["GS_KEEP"] == "env" and "GS_KEEP" not in loaded
    for k in ("GS_A", "GS_B", "GS_C"):
        monkeypatch.delenv(k)
