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
    tool_msgs = [m for m in msgs if m["role"] == "user" and isinstance(m["content"], list)
                 and m["content"][0].get("type") == "tool_result"]
    assert len(tool_msgs) == 1 and len(tool_msgs[0]["content"]) == 2  # both results in ONE message
    assert r["tokens"] == {"input": 550, "cache_read": 900, "cache_write": 400, "output": 40}
    assert agent.store.pref("day_end") == "22:00"


def test_loop_sends_effort_thinking_and_cache_points(state):
    client = FakeClient([text_resp("hi")])
    StudyAgent(client, state, CFG, "2026-10-30").ask("hi")
    req = client.messages.requests[0]
    assert req["output_config"] == {"effort": "medium"} and req["thinking"] == {"type": "adaptive"}
    assert req["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}


# ---------- tools.py ----------
def test_tool_errors_return_is_error_and_loop_continues(state):
    client = FakeClient([
        tool_resp(("a", "add_task", {"title": "X", "course": "C", "due": "next week", "hours": 2}),
                  ("b", "no_such_tool", {})),
        text_resp("fixed"),
    ])
    agent = StudyAgent(client, state, CFG, "2026-10-30")
    assert agent.ask("x")["answer"] == "fixed"
    second_req = client.messages.requests[1]["messages"]
    results = second_req[-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "YYYY-MM-DD" in results[0]["content"] and "unknown tool" in results[1]["content"]


def test_tool_schemas_are_valid_api_format():
    s = schemas()
    assert len(s) == 8
    assert {x["name"] for x in s} >= {"add_task", "read_calendar", "lookup_topic", "remember"}
    assert all(x["input_schema"]["type"] == "object" for x in s)


def test_tool_output_is_compact_and_capped(state):
    store = StudyStore(state, "2026-10-30")
    box = Toolbox(StudyDomain(store, fetch=fake_fetch))
    out = box.execute({"id": "1", "name": "lookup_topic", "input": {"topic": "dynamic programming"}})
    assert len(out["content"]) < 800 and "source:" in out["content"]
    again = box.execute({"id": "2", "name": "lookup_topic", "input": {"topic": "Dynamic Programming"}})
    assert "(cached)" in again["content"]


# ---------- history.py ----------
def test_history_is_append_only_and_reloads(state):
    h = History(state / "c.jsonl")
    h.append("user", "hello")
    h.append("assistant", [{"type": "text", "text": "hi"}])
    before = (state / "c.jsonl").read_text()
    h.append("user", "again")
    assert (state / "c.jsonl").read_text().startswith(before)  # old lines untouched
    assert len(History(state / "c.jsonl").messages()) == 3      # a new instance reads the same conversation


# ---------- compaction.py ----------
def test_compaction_summarises_old_turns_and_keeps_last(state):
    h = History(state / "c.jsonl")
    for i in range(3):
        h.append("user", [{"type": "text", "text": f"question {i}"}])
        h.append("assistant", [{"type": "tool_use", "id": f"u{i}", "name": "recall", "input": {}}])
        h.append("user", [{"type": "tool_result", "tool_use_id": f"u{i}", "content": "x"}])
        h.append("assistant", [{"type": "text", "text": f"answer {i}"}])
    lines_before = len(h.records())
    client = FakeClient([text_resp("student asked 3 things")])
    meter = TurnMeter("claude-opus-5-5")
    assert not compaction.maybe_compact(client, "m", h, meter, 100, threshold=1000)
    assert compaction.maybe_compact(client, "m", h, meter, 5000, threshold=1000)
    msgs = h.messages()
    assert "student asked 3 things" in msgs[0]["content"]
    assert msgs[2]["content"][0]["text"] == "question 2"   # last turn kept intact (tool pair not split)
    assert len(msgs) == 2 + 4
    assert len(h.records()) == lines_before + 1             # appended, nothing rewritten
    assert meter.calls == 1


# ---------- caching.py ----------
def test_caching_does_not_mutate_history():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "a"}]}]
    tools, system, out = caching.apply([{"name": "t"}], "sys", msgs)
    assert "cache_control" not in msgs[0]["content"][0]
    assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}


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
    first_msg = c2.messages.requests[0]["messages"]
    assert len(first_msg) == 1                            # no old conversation...
    assert "day_end=22:00" in first_msg[0]["content"][0]["text"]  # ...but memory is there


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
    r = json.loads(out.read_text())
    assert r["checks_passed"] == "1/1"
    assert set(r["turns"][0]) >= {"tokens", "model_calls", "tools", "cost_usd", "seconds", "session", "turn"}
    assert r["totals"]["model_calls"] == 3
