"""Repository plugin bundle contract tests."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parents[1] / "plugins" / "rulegarden"


def test_plugin_manifest_and_mcp_config_reference_the_installed_commands() -> None:
    manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "rulegarden"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "hooks" not in manifest
    assert mcp_config["mcpServers"]["rulegarden"]["command"] == "rulegarden-mcp"


def test_plugin_hooks_and_skill_cover_the_complete_rule_lifecycle() -> None:
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    skill = (PLUGIN_ROOT / "skills" / "rulegarden" / "SKILL.md").read_text(encoding="utf-8")

    assert {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}.issubset(hooks["hooks"])
    assert "rulegarden_begin_task" in skill
    assert "rulegarden_finish_task" in skill
    assert "project_root" in skill
