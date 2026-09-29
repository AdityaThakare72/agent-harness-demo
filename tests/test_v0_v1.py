import pytest

import v0_model_only
import v1_loop
from harness.model import FakeModel, reply
from tests.conftest import last_tool_output


def test_v0_single_call_no_tools(trace):
    model = FakeModel([reply("hello")])
    assert v0_model_only.run("hi", model, trace) == "hello"
    assert len(model.seen) == 1 and model.seen[0]["tools"] == []


def test_v1_loop_reads_file_then_answers(sandbox, trace):
    path = str(sandbox / "bug_report.txt")
    model = FakeModel([reply("", ("read_file", {"path": path})), reply("done")])
    assert v1_loop.run_agent("summarize", model, trace) == "done"
    assert "off-by-one" in last_tool_output(model)
    assert trace.kinds() == ["model", "call", "result", "model"]


def test_v1_bad_path_crashes_the_loop(trace):
    model = FakeModel([reply("", ("read_file", {"path": "/no/such/file.txt"}))])
    with pytest.raises(FileNotFoundError):
        v1_loop.run_agent("go", model, trace)
