"""A CLI app is a third-party binary, so it runs under the exec sandbox."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nanobot.agent import plugins as agent_plugins
from nanobot.apps.cli.service import CliAppManager, CliAppsRuntimeConfig

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="no sandbox backend exists on Windows"
)


@pytest.fixture(autouse=True)
def _isolate_plugin_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_plugins, "get_config_path", lambda: tmp_path / "config/config.json")


def _manager(tmp_path: Path, sandbox: str) -> CliAppManager:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return CliAppManager(
        workspace=workspace,
        data_dir=tmp_path / "data",
        runtime=CliAppsRuntimeConfig(sandbox=sandbox),
    )


def _stub_run(manager: CliAppManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr(manager, "get_app", lambda name: {"name": name, "entry_point": "acme"})
    monkeypatch.setattr(manager, "_load_installed", lambda: {"acme": {"entry_point": "acme"}})
    monkeypatch.setattr("nanobot.apps.cli.service.shutil.which", lambda entry: "/usr/bin/acme")
    monkeypatch.setattr(manager, "_resolve_cwd", lambda *a, **k: tmp_path / "workspace")
    monkeypatch.setattr(manager, "_artifact_snapshot", lambda cwd: {})
    monkeypatch.setattr(manager, "_changed_artifacts", lambda cwd, snap: [])
    monkeypatch.setattr("nanobot.apps.cli.service.subprocess.run", fake_run)
    return captured


@posix_only
def test_run_wraps_argv_in_the_configured_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, "bwrap")
    captured = _stub_run(manager, tmp_path, monkeypatch)

    manager.run("acme", ["--version"])

    argv = captured["argv"]
    assert argv[1] == "-c"
    assert argv[2].startswith("bwrap ")
    assert "/usr/bin/acme --version" in argv[2]


def test_run_is_unwrapped_when_no_sandbox_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path, "")
    captured = _stub_run(manager, tmp_path, monkeypatch)

    manager.run("acme", ["--version"])

    assert captured["argv"] == ["/usr/bin/acme", "--version"]
