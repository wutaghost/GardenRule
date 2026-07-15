"""Local STDIO MCP server exposing RuleGarden's task lifecycle tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from rulegarden.app import RuleGardenApplication
from rulegarden.models import RuleScope


SERVER_INSTRUCTIONS = (
    "At the start of a coding task call rulegarden_begin_task. "
    "When the user corrects agent behavior or asks to remember a rule, call "
    "rulegarden_record_correction. Before ending a task with a rule event, "
    "call rulegarden_finish_task."
)


def create_server(project_root: Path | None = None) -> FastMCP:
    """Create an MCP server whose tools share one project-scoped application service."""
    root = project_root or Path(os.environ.get("RULEGARDEN_PROJECT_ROOT", Path.cwd()))
    app = RuleGardenApplication(root)
    server = FastMCP("RuleGarden", instructions=SERVER_INSTRUCTIONS)

    @server.tool()
    def rulegarden_initialize() -> dict[str, Any]:
        """Initialize RuleGarden state for the configured project."""
        return app.initialize()

    @server.tool()
    def rulegarden_begin_task(
        task_summary: str,
        task_types: list[str] | None = None,
        expected_paths: list[str] | None = None,
        risk_signals: list[str] | None = None,
    ) -> dict[str, Any]:
        """Start a task and load only relevant dynamic or stable rule guidance."""
        return app.begin_task(task_summary, task_types or [], expected_paths or [], risk_signals or [])

    @server.tool()
    def rulegarden_record_correction(
        task_id: str,
        candidate_instruction: str,
        evidence_summary: str,
        affected_paths: list[str] | None = None,
        scope_paths: list[str] | None = None,
        scope_task_types: list[str] | None = None,
        severity: str = "normal",
    ) -> dict[str, Any]:
        """Record a redacted correction and create a dynamic learned rule."""
        return app.record_correction(
            task_id,
            candidate_instruction,
            RuleScope(paths=scope_paths or [], task_types=scope_task_types or []),
            evidence_summary,
            affected_paths or [],
            severity,
        )

    @server.tool()
    def rulegarden_finish_task(task_id: str) -> dict[str, Any]:
        """Finish a task and remove its ignored runtime state."""
        return app.finish_task(task_id)

    @server.tool()
    def rulegarden_list_rules(status: str | None = None) -> dict[str, Any]:
        """List concise project rule summaries."""
        return app.list_rules(status)

    @server.tool()
    def rulegarden_transition_rule(rule_id: str, target_status: str) -> dict[str, Any]:
        """Promote, demote, disable, or delete a rule through a reversible transaction."""
        return app.transition_rule(rule_id, target_status)

    @server.tool()
    def rulegarden_undo(transaction_id: str | None = None) -> dict[str, Any]:
        """Undo the latest or named RuleGarden transaction."""
        return app.undo(transaction_id)

    return server


mcp = create_server()


def main() -> None:
    """Run the server over the transport configured by Codex's local MCP process."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
