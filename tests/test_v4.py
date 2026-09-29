from dataclasses import replace

import v4_context
from harness.model import FakeModel, Message, ToolResult, reply
from tests.conftest import last_tool_output

YES = lambda call: True


def pair(i, size=1000):
    call_id = f"c{i}"
    model_msg = reply("", ("read_file", {"path": f"f{i}.txt"}))
    model_msg.tool_calls[0].id = call_id
    return [model_msg, Message("tool", tool_results=[ToolResult(call_id, "read_file", "x" * size)])]


def history(n_pairs, size=1000):
    msgs = [Message("user", "the task")]
    for i in range(n_pairs):
        msgs += pair(i, size)
    return msgs


def test_trim_leaves_small_history_untouched():
    msgs = history(2, size=10)
    assert v4_context.trim(msgs, max_chars=10_000) is msgs


def test_trim_shrinks_old_outputs_and_keeps_recent_verbatim():
    msgs = history(6)
    out = v4_context.trim(msgs, max_chars=4000, keep_turns=2)
    assert len(out) == len(msgs)
    assert out[2].tool_results[0].output == "[output trimmed]"
    assert out[-1].tool_results[0].output == "x" * 1000
    assert out[-3].tool_results[0].output == "x" * 1000


def test_trim_drops_oldest_pairs_when_still_over_budget_and_stays_valid():
    msgs = history(10)
    out = v4_context.trim(msgs, max_chars=2100, keep_turns=2)
    assert v4_context.total(out) <= 2100
    assert len(out) < len(msgs)
    assert out[0].text.startswith("the task") and "earlier messages trimmed" in out[0].text
    assert out[-2:] == msgs[-2:]
    body = out[1:]
    for model_msg, tool_msg in zip(body[0::2], body[1::2]):
        assert model_msg.role == "model" and tool_msg.role == "tool"
        assert tool_msg.tool_results[0].call_id == model_msg.tool_calls[0].id


def test_trim_does_not_mutate_original_history():
    msgs = history(6)
    v4_context.trim(msgs, max_chars=2100)
    assert all(m.tool_results[0].output == "x" * 1000 for m in msgs if m.tool_results)


def test_todo_tool_updates_plan_and_reports_it(sandbox, trace):
    todos = [{"text": "read", "status": "in_progress"}, {"text": "write", "status": "pending"}]
    model = FakeModel([reply("", ("update_todos", {"todos": todos})), reply("ok")])
    v4_context.run_agent("go", model, sandbox, YES, trace)
    assert last_tool_output(model) == "[~] read\n[ ] write"


def test_plan_is_shown_to_model_on_every_later_turn(sandbox, trace):
    todos = [{"text": "read", "status": "done"}]
    model = FakeModel([reply("", ("update_todos", {"todos": todos})), reply("ok")])
    v4_context.run_agent("go", model, sandbox, YES, trace)
    assert "Current todo list" not in model.seen[0]["system"]
    assert "[x] read" in model.seen[1]["system"]


def test_invalid_todo_status_is_returned_as_error(sandbox, trace):
    bad = [{"text": "read", "status": "maybe"}]
    model = FakeModel([reply("", ("update_todos", {"todos": bad})), reply("ok")])
    result = v4_context.run_agent("go", model, sandbox, YES, trace)
    assert last_tool_output(model).startswith("Error: ToolError")
    assert result.stop == "done"


def test_agent_sends_trimmed_history_but_still_finishes(sandbox, trace):
    reads = [reply("", ("read_file", {"path": "bug_report.txt"})) for _ in range(6)]
    model = FakeModel(reads + [reply("done")])
    result = v4_context.run_agent("go", model, sandbox, YES, trace, max_chars=600)
    assert (result.text, result.stop) == ("done", "done")
    assert "trim" in trace.kinds()
    assert len(model.seen[-1]["messages"]) < 2 * 6 + 1


def test_v4_keeps_v3_guardrails(sandbox, trace):
    model = FakeModel([reply("", ("read_file", {"path": "../x"})), reply("", ("write_file", {"path": "a", "content": "b"})), reply("ok")])
    v4_context.run_agent("go", model, sandbox, lambda c: False, trace)
    assert "outside the sandbox" in last_tool_output(model, 1)
    assert "permission denied" in last_tool_output(model, 2)


def test_v4_step_limit(sandbox, trace):
    model = FakeModel([reply("", ("list_dir", {"path": "."}))], repeat_last=True)
    result = v4_context.run_agent("go", model, sandbox, YES, trace, max_steps=4)
    assert (result.stop, result.steps) == ("max_steps", 4)
