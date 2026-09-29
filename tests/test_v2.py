import pytest

import v2_tools
from harness.model import FakeModel, reply
from tests.conftest import last_tool_output


def test_v2_write_list_shell(tmp_path, trace):
    out = tmp_path / "out.txt"
    model = FakeModel([
        reply("", ("write_file", {"path": str(out), "content": "hi"})),
        reply("", ("list_dir", {"path": str(tmp_path)})),
        reply("", ("run_shell", {"command": f"cat {out}"})),
        reply("done"),
    ])
    assert v2_tools.run_agent("go", model, trace) == "done"
    assert out.read_text() == "hi"
    assert "out.txt" in last_tool_output(model, 2)
    assert "hi" in last_tool_output(model, 3)


def test_v2_has_four_tools(trace):
    model = FakeModel([reply("ok")])
    v2_tools.run_agent("go", model, trace)
    assert model.seen[0]["tools"] == ["read_file", "write_file", "list_dir", "run_shell"]


def test_v2_tool_error_crashes(trace):
    model = FakeModel([reply("", ("list_dir", {"path": "/no/such/dir"}))])
    with pytest.raises(FileNotFoundError):
        v2_tools.run_agent("go", model, trace)
