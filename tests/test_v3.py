import pytest

import v3_safety
from harness.model import FakeModel, ToolCall, reply
from tests.conftest import last_tool_output

YES = lambda call: True
NO = lambda call: False


def run(model, sandbox, trace, approve=YES, max_steps=10):
    return v3_safety.run_agent("go", model, sandbox, approve, trace, max_steps)


def test_happy_path_writes_report(sandbox, trace):
    model = FakeModel([
        reply("", ("list_dir", {"path": "."})),
        reply("", ("read_file", {"path": "bug_report.txt"})),
        reply("", ("write_file", {"path": "report.md", "content": "# report"})),
        reply("all done"),
    ])
    result = run(model, sandbox, trace)
    assert (result.text, result.steps, result.stop) == ("all done", 4, "done")
    assert (sandbox / "report.md").read_text() == "# report"
    assert "bug_report.txt" in last_tool_output(model, 1)


def test_bad_path_is_returned_to_model_and_loop_continues(sandbox, trace):
    model = FakeModel([reply("", ("read_file", {"path": "missing.txt"})), reply("recovered")])
    result = run(model, sandbox, trace)
    assert result.stop == "done" and result.text == "recovered"
    assert last_tool_output(model).startswith("Error: FileNotFoundError")
    assert model.seen[1]["messages"][-1].tool_results[0].is_error
    assert "error" in trace.kinds()


@pytest.mark.parametrize("path", ["../secret.txt", "/etc/hostname", "sub/../../secret.txt"])
def test_paths_outside_sandbox_are_blocked(sandbox, trace, path):
    (sandbox.parent / "secret.txt").write_text("top secret")
    model = FakeModel([reply("", ("read_file", {"path": path})), reply("ok")])
    run(model, sandbox, trace)
    assert "outside the sandbox" in last_tool_output(model)
    assert "top secret" not in last_tool_output(model)


def test_write_outside_sandbox_is_blocked(sandbox, trace):
    model = FakeModel([reply("", ("write_file", {"path": "../evil.txt", "content": "x"})), reply("ok")])
    run(model, sandbox, trace)
    assert not (sandbox.parent / "evil.txt").exists()


def test_symlink_escape_is_blocked(sandbox, trace):
    (sandbox.parent / "secret.txt").write_text("top secret")
    (sandbox / "link.txt").symlink_to(sandbox.parent / "secret.txt")
    model = FakeModel([reply("", ("read_file", {"path": "link.txt"})), reply("ok")])
    run(model, sandbox, trace)
    assert "outside the sandbox" in last_tool_output(model)


def test_denied_write_does_not_happen_and_model_is_told(sandbox, trace):
    model = FakeModel([reply("", ("write_file", {"path": "report.md", "content": "x"})), reply("gave up")])
    result = run(model, sandbox, trace, approve=NO)
    assert not (sandbox / "report.md").exists()
    assert last_tool_output(model) == "Error: permission denied by user"
    assert result.text == "gave up"
    assert "denied" in trace.kinds()


def test_denied_shell_does_not_run(sandbox, trace):
    model = FakeModel([reply("", ("run_shell", {"command": "touch pwned"})), reply("ok")])
    run(model, sandbox, trace, approve=NO)
    assert not (sandbox / "pwned").exists()


def test_reads_never_ask_for_permission(sandbox, trace):
    asked = []
    model = FakeModel([reply("", ("read_file", {"path": "bug_report.txt"}), ("list_dir", {"path": "."})), reply("ok")])
    run(model, sandbox, trace, approve=lambda c: asked.append(c) or True)
    assert asked == []


def test_approval_is_asked_for_write_and_shell(sandbox, trace):
    asked = []
    model = FakeModel([
        reply("", ("write_file", {"path": "a.txt", "content": "x"}), ("run_shell", {"command": "echo hi"})),
        reply("ok"),
    ])
    run(model, sandbox, trace, approve=lambda c: asked.append(c.name) or True)
    assert asked == ["write_file", "run_shell"]
    outputs = [r.output for r in model.seen[1]["messages"][-1].tool_results]
    assert "hi" in outputs[1]


def test_shell_runs_inside_sandbox_folder(sandbox, trace):
    model = FakeModel([reply("", ("run_shell", {"command": "ls"})), reply("ok")])
    run(model, sandbox, trace)
    assert "bug_report.txt" in last_tool_output(model)


def test_step_limit_stops_a_looping_model(sandbox, trace):
    model = FakeModel([reply("", ("list_dir", {"path": "."}))], repeat_last=True)
    result = run(model, sandbox, trace, max_steps=3)
    assert (result.stop, result.steps) == ("max_steps", 3)
    assert len(model.seen) == 3
    assert "max_steps=3" in result.text
    assert trace.kinds()[-1] == "stop"


def test_unknown_tool_returns_error(sandbox, trace):
    model = FakeModel([reply("", ("format_disk", {})), reply("ok")])
    run(model, sandbox, trace)
    assert "unknown tool" in last_tool_output(model)


def test_bad_arguments_return_error(sandbox, trace):
    model = FakeModel([reply("", ("read_file", {})), reply("ok")])
    run(model, sandbox, trace)
    assert last_tool_output(model).startswith("Error: TypeError")


def test_parallel_tool_calls_all_get_results(sandbox, trace):
    model = FakeModel([
        reply("", ("read_file", {"path": "bug_report.txt"}), ("read_file", {"path": "reading_list.txt"})),
        reply("ok"),
    ])
    run(model, sandbox, trace)
    results = model.seen[1]["messages"][-1].tool_results
    assert [r.call_id for r in results] == ["call_0", "call_1"]


def test_long_tool_output_is_truncated(sandbox, trace):
    (sandbox / "big.txt").write_text("x" * 50_000)
    model = FakeModel([reply("", ("read_file", {"path": "big.txt"})), reply("ok")])
    run(model, sandbox, trace)
    assert len(last_tool_output(model)) == v3_safety.MAX_OUTPUT


def test_trace_records_every_turn_call_and_result(sandbox, trace):
    model = FakeModel([reply("", ("read_file", {"path": "bug_report.txt"})), reply("done")])
    run(model, sandbox, trace)
    assert trace.kinds() == ["model", "call", "result", "model"]
