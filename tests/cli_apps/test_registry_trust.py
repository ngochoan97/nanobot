"""Registry entries are untrusted input.

A lower-trust registry must not borrow the trusted label when it shadows an
entry, and no registry may name an interpreter as a CLI app's entry point.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from nanobot.agent import plugins as agent_plugins
from nanobot.apps.cli.service import (
    CliAppError,
    CliAppManager,
    CliAppsRuntimeConfig,
    _validated_entry_point,
)


@pytest.fixture(autouse=True)
def _isolate_plugin_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_plugins, "get_config_path", lambda: tmp_path / "config/config.json")


def _manager(tmp_path: Path) -> CliAppManager:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return CliAppManager(
        workspace=workspace,
        data_dir=tmp_path / "data",
        runtime=CliAppsRuntimeConfig(catalog_ttl_seconds=3600),
    )


def _write_cache(manager: CliAppManager, source: str, clis: list[dict]) -> None:
    path = manager._cache_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_cached_at": time.time(), "data": {"clis": clis}}),
        encoding="utf-8",
    )


# --- trust label ------------------------------------------------------------

def test_shadowed_entry_reports_the_lower_trust_registry(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    official = {
        "name": "acme",
        "display_name": "Acme",
        "package_manager": "npm",
        "npm_package": "acme-official",
        "entry_point": "acme",
    }
    shadow = {**official, "npm_package": "attacker-pkg", "skill_md": "skills/evil/SKILL.md"}
    _write_cache(manager, "harness", [official])
    _write_cache(manager, "public", [])
    _write_cache(manager, "extensions", [shadow])

    app = manager.catalog(cache_only=True)[0][0]

    # the extensions registry supplied every field, so it owns the trust label
    assert app["npm_package"] == "attacker-pkg"
    assert app["_source"] == "harness+extensions"
    assert manager._trust_registry(app) == "nanobot-extension"
    assert manager._manifest_source(app) == "nanobot-extension"


def test_single_source_labels_are_unchanged(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    _write_cache(manager, "harness", [{"name": "acme", "entry_point": "acme"}])
    _write_cache(manager, "public", [])
    _write_cache(manager, "extensions", [])

    app = manager.catalog(cache_only=True)[0][0]

    assert manager._trust_registry(app) == "cli-anything"
    assert manager._manifest_source(app) == "cli-anything:harness"


# --- entry point validation -------------------------------------------------

@pytest.mark.parametrize(
    "blocked",
    ["bash", "sh", "PowerShell", "pwsh", "python3", "node", "cmd.exe", "git", "npx", "env", "sudo"],
)
def test_interpreters_are_rejected(blocked: str) -> None:
    assert _validated_entry_point(blocked) == ""


@pytest.mark.parametrize(
    "unsafe",
    ["../../bin/bash", "/bin/sh", r"C:\Windows\system32\cmd.exe", "acme tool", "acme;rm -rf /", "", "   "],
)
def test_non_bare_names_are_rejected(unsafe: str) -> None:
    assert _validated_entry_point(unsafe) == ""


@pytest.mark.parametrize("name", ["acme", "cli-anything-acme", "gemini_cli", "tool.v2", "Acme2"])
def test_plain_cli_names_are_accepted(name: str) -> None:
    assert _validated_entry_point(name) == name


def test_run_refuses_an_interpreter_entry_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    monkeypatch.setattr(manager, "get_app", lambda name: {"name": name, "entry_point": "bash"})
    monkeypatch.setattr(manager, "_load_installed", lambda: {"acme": {"entry_point": "bash"}})
    monkeypatch.setattr(manager, "_resolve_cwd", lambda *a, **k: tmp_path)

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess must not run for an unsafe entry point")

    monkeypatch.setattr("nanobot.apps.cli.service.subprocess.run", _fail)

    with pytest.raises(CliAppError, match="unsafe entry point"):
        manager.run("acme", ["-c", "echo pwned"])


def test_install_does_not_auto_record_an_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bash` is always on PATH, so the "already available" shortcut would
    otherwise install a shell as a CLI app without running anything."""
    manager = _manager(tmp_path)
    app = {"name": "acme", "display_name": "Acme", "entry_point": "bash", "package_manager": "bundled"}
    monkeypatch.setattr(manager, "get_app", lambda name: app)
    recorded: list[object] = []
    monkeypatch.setattr(manager, "_record_installed", lambda a: recorded.append(a))

    with pytest.raises(CliAppError):
        manager.install("acme")

    assert recorded == []
