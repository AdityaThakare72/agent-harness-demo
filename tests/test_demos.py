import shutil

import pytest

import v0_model_only, v1_loop, v2_tools, v3_safety, v4_context
from tests.conftest import REPO


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    shutil.copytree(REPO / "sandbox", tmp_path / "sandbox", ignore=shutil.ignore_patterns("report.md"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("stage", [v0_model_only, v1_loop, v2_tools])
def test_fake_demo_runs_offline(stage, cwd, capsys):
    stage.main(["--fake"])
    assert capsys.readouterr().out.strip()


def test_v2_demo_writes_report(cwd):
    v2_tools.main(["--fake"])
    assert "Sandbox summary" in (cwd / "sandbox" / "report.md").read_text()


@pytest.mark.parametrize("stage", [v3_safety, v4_context])
def test_fake_demo_v3_v4_writes_report(stage, cwd, capsys):
    stage.main(["--fake", "--yes"])
    assert "Finished" in capsys.readouterr().out
    assert "Sandbox summary" in (cwd / "sandbox" / "report.md").read_text()


def test_v3_demo_denied_by_user_writes_nothing(cwd, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    v3_safety.main(["--fake"])
    assert not (cwd / "sandbox" / "report.md").exists()
