"""The marketplace installer runs third-party code and must not hand it secrets.

`tests/apps/test_cli_subprocess_env.py` pins the same invariant for CLI apps;
the skills installer shells out to `npx` and has to honour it too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nanobot.webui import skills_marketplace


class _Process:
    returncode = 0

    async def communicate(self) -> tuple[bytes, None]:
        return b"installed", None

    def kill(self) -> None:  # pragma: no cover - only used on timeout
        pass


async def test_installer_env_excludes_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-leak")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-leak")
    captured: dict[str, Any] = {}

    async def fake_exec(*command: str, **kwargs: Any) -> _Process:
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return _Process()

    monkeypatch.setattr(skills_marketplace.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(skills_marketplace.asyncio, "create_subprocess_exec", fake_exec)

    # The installer reports failure because no skill lands on disk; the
    # environment it passed is what this test is about.
    with pytest.raises(skills_marketplace.SkillsMarketplaceError):
        await skills_marketplace.install_marketplace_skill(
            "acme/agent-skills", "react-testing", tmp_path
        )

    env = captured["env"]
    assert isinstance(env, dict)
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert not any("KEY" in name or "TOKEN" in name for name in env)
    # still usable: npx needs a PATH, and telemetry stays off
    assert env.get("PATH")
    assert env.get("DISABLE_TELEMETRY") == "1"
