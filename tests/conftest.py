import shutil
from pathlib import Path

import pytest

from harness.trace import Trace

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def sandbox(tmp_path):
    dest = tmp_path / "sandbox"
    shutil.copytree(REPO / "sandbox", dest, ignore=shutil.ignore_patterns("report.md"))
    return dest


@pytest.fixture
def trace():
    return Trace(quiet=True)


def last_tool_output(model, call_index=-1):
    return model.seen[call_index]["messages"][-1].tool_results[0].output
