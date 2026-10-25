"""API harness, tested file by file with a fake client."""
from __future__ import annotations

import json

from conftest import CFG, FakeClient, fake_fetch, text_resp, tool_resp

from API.agent import StudyAgent
from API.harness import caching, compaction
from API.harness.context import ContextBuilder
from API.harness.history import History
from API.harness.memory import Memory
from API.harness.tokens import TurnMeter
from API.harness.tools import Toolbox, schemas
from shared.domain import StudyDomain
from shared.store import StudyStore


# ---------- loop.py ----------
def test_loop_runs_until_end_turn_and_batches_tool_results(state):
    client = FakeClient([
        tool_resp(("t1", "add_task", {"title": "HW3", "course": "Algo", "due": "2026-11-03", "hours": 6}),
                  ("t2", "remember", {"key": "day_end", "value": "22:00"}), inp=500, write=400),
        text_resp("done", inp=50, read=900),
    ])
    agent = StudyAgent(client, state, CFG, "2026-10-30")
    r = agent.ask("add HW3 and remember 22:00")
    assert r["answer"] == "done"
    assert r["model_calls"] == 2
    assert r["tools"] == ["add_task", "remember"]
    msgs = agent.history.messages()
    tool_msgs = [m for m in msgs if m["role"] == "user" and "functionResponse" in m["parts"][0]]
    assert len(tool_msgs) == 1 and len(tool_msgs[0]["parts"]) == 2  # both results in ONE message
    assert any(p.get("thoughtSignature") == "sig" for m in msgs if m["role"] == "model" for p in m["parts"])
    assert r["tokens"] == {"input": 550, "cache_read": 900, "cache_write": 0, "output": 40}
    assert agent.store.pref("day_end") == "22:00"


def test_loop_sends_thinking_level_tools_and_system(state):
    client = FakeClient([text_resp("hi")])
    StudyAgent(client, state, CFG, "2026-10-30").ask("hi")
    req = client.requests[0]
    assert req["thinking_level"] == "medium" and req["model"] == CFG["model"]
    assert len(req["tools"][0]["functionDeclarations"]) == 8 and "Study Compass" in req["system"]
    assert req["contents"][-1]["role"] == "user"


# ---------- tools.py ----------
def test_tool_errors_return_is_error_and_loop_continues(state):
    client = FakeClient([
        tool_resp(("a", "add_task", {"title": "X", "course": "C", "due": "next week", "hours": 2}),
                  ("b", "no_such_tool", {})),
        text_resp("fixed"),
    ])
    agent = StudyAgent(client, state, CFG, "2026-10-30")
    assert agent.ask("x")["answer"] == "fixed"
    results = client.requests[1]["contents"][-1]["parts"]
    resp = [r["functionResponse"] for r in results]
    assert all("error" in r["response"] for r in resp)
    assert "YYYY-MM-DD" in resp[0]["response"]["error"] and "unknown tool" in resp[1]["response"]["error"]


def test_tool_schemas_are_valid_api_format():
    decls = schemas()[0]["functionDeclarations"]
    assert len(decls) == 8
    assert {x["name"] for x in decls} >= {"add_task", "read_calendar", "lookup_topic", "remember"}
    assert all(x["parametersJsonSchema"]["type"] == "object" for x in decls if x["name"] != "recall")
    assert "parametersJsonSchema" not in next(x for x in decls if x["name"] == "recall")


def test_tool_output_is_compact_and_capped(state):
    store = StudyStore(state, "2026-10-30")
    box = Toolbox(StudyDomain(store, fetch=fake_fetch))
    out = box.execute({"id": "1", "name": "lookup_topic", "args": {"topic": "dynamic programming"}})["functionResponse"]
    text = out["response"]["result"]
    assert out["id"] == "1" and len(text) < 800 and "source:" in text
    again = box.execute({"name": "lookup_topic", "args": {"topic": "Dynamic Programming"}})["functionResponse"]
    assert "(cached)" in again["response"]["result"]


# ---------- history.py ----------
def test_history_is_append_only_and_reloads(state):
    h = History(state / "c.jsonl")
    h.append("user", [{"text": "hello"}])
    h.append("model", [{"text": "hi"}])
    before = (state / "c.jsonl").read_text(encoding="utf-8")
    h.append("user", [{"text": "again"}])
    assert (state / "c.jsonl").read_text(encoding="utf-8").startswith(before)  # old lines untouched
    assert len(History(state / "c.jsonl").messages()) == 3      # a new instance reads the same conversation


# ---------- compaction.py ----------
def test_compaction_summarises_old_turns_and_keeps_last(state):
    h = History(state / "c.jsonl")
    for i in range(3):
        h.append("user", [{"text": f"question {i}"}])
        h.append("model", [{"functionCall": {"name": "recall", "args": {}}}])
        h.append("user", [{"functionResponse": {"name": "recall", "response": {"result": "x"}}}])
        h.append("model", [{"text": f"answer {i}"}])
    lines_before = len(h.records())
    client = FakeClient([text_resp("student asked 3 things")])
    meter = TurnMeter(CFG["model"])
    assert not compaction.maybe_compact(client, "m", h, meter, 100, threshold=1000)
    assert compaction.maybe_compact(client, "m", h, meter, 5000, threshold=1000)
    msgs = h.messages()
    assert "student asked 3 things" in msgs[0]["parts"][0]["text"]
    assert msgs[2]["parts"][0]["text"] == "question 2"   # last turn kept intact (tool pair not split)
    assert len(msgs) == 2 + 4
    assert len(h.records()) == lines_before + 1             # appended, nothing rewritten
    assert meter.calls == 1


# ---------- caching.py ----------
def test_caching_is_implicit_and_resends_a_stable_prefix(state):
    msgs = [{"role": "user", "parts": [{"text": "a"}]}]
    assert caching.apply([{"name": "t"}], "sys", msgs) == ([{"name": "t"}], "sys", msgs)
    client = FakeClient([text_resp("a", inp=300), text_resp("b", inp=20, read=300)])
    agent = StudyAgent(client, state, CFG, "2026-10-30")
    agent.ask("one")
    r = agent.ask("two")
    assert r["tokens"]["cache_read"] == 300 and r["tokens"]["input"] == 20
    first, second = client.requests[0]["contents"], client.requests[1]["contents"]
    assert second[:len(first)] == first  # earlier messages are resent unchanged (what implicit caching needs)


# ---------- memory.py + context.py ----------
def test_memory_contradiction_keeps_history_and_digest_shows_it(state):
    store = StudyStore(state, "2026-10-30")
    store.remember("day_end", "22:00")
    store.remember("day_end", "23:00")
    store.remember("note", "struggles with recursion in algorithms")
    store.remember("note", "likes studying in the library")
    d = Memory(store).digest("help me with recursion please")
    assert "day_end=23:00 (was 22:00)" in d
    assert "recursion" in d and "library" not in d and "1 other notes" in d


def test_context_injects_only_relevant_tasks_not_calendar(state):
    store = StudyStore(state, "2026-10-30")
    store.add_task("Soon", "A", "2026-11-02", 2)
    store.add_task("Far away", "B", "2027-01-20", 5)
    done = store.add_task("Old", "C", "2026-10-31", 1)
    store.complete_task(done["id"])
    content = ContextBuilder(store, Memory(store)).build_user_content("plan please")
    ctx = content[0]["text"]
    assert "Soon" in ctx and "Far away" not in ctx and "Old" not in ctx
    assert "lecture" not in ctx  # timetable is fetched by tool, not injected
    assert content[1]["text"] == "plan please"


def test_session2_fresh_instance_gets_memory_from_disk(state):
    a1 = StudyAgent(FakeClient([tool_resp(("x", "remember", {"key": "day_end", "value": "22:00"})), text_resp("ok")]),
                    state, CFG, "2026-10-30")
    a1.ask("no studying after 22:00")
    c2 = FakeClient([text_resp("your limit is 22:00")])
    a2 = StudyAgent(c2, state, CFG, "2026-10-30")       # new instance, new conversation
    a2.ask("what did I tell you?")
    first_msg = c2.requests[0]["contents"]
    assert len(first_msg) == 1                            # no old conversation...
    assert "day_end=22:00" in first_msg[0]["parts"][0]["text"]  # ...but memory is there


def test_results_json_shape_via_runner(state, tmp_path):
    import asyncio
    from shared.scenario_runner import run_scenario
    scen = tmp_path / "s.json"
    scen.write_text(json.dumps({"today": "2026-10-30", "sessions": [{"turns": ["a"]}, {"turns": ["b"]}],
                                "checks": [{"id": "c", "type": "pref_equals", "key": "day_end", "value": "22:00"}]}))
    script = [tool_resp(("x", "remember", {"key": "day_end", "value": "22:00"})), text_resp("ok"), text_resp("ok2")]
    client = FakeClient(script)
    out = tmp_path / "r.json"
    asyncio.run(run_scenario(scen, out, state, lambda s, t, n: StudyAgent(client, s, CFG, t), "API", {}, {}))
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["checks_passed"] == "1/1"
    assert set(r["turns"][0]) >= {"tokens", "model_calls", "tools", "cost_usd", "seconds", "session", "turn"}
    assert r["totals"]["model_calls"] == 3
