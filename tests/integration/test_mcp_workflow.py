"""STDIO MCP integration test using a real RuleGarden subprocess."""

from __future__ import annotations

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_server_lists_and_invokes_the_initialize_tool(tmp_path) -> None:
    async def exercise_server() -> None:
        # The test process receives src through conftest; the child needs it explicitly.
        from pathlib import Path
        import os
        import sys

        source_root = Path(__file__).parents[2] / "src"
        environment = os.environ | {
            "PYTHONPATH": str(source_root),
            "RULEGARDEN_PROJECT_ROOT": str(tmp_path / "wrong-default-root"),
        }
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rulegarden.mcp.server"],
            cwd=source_root,
            env=environment,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {
                    "rulegarden_initialize",
                    "rulegarden_begin_task",
                    "rulegarden_record_correction",
                    "rulegarden_finish_task",
                    "rulegarden_transition_rule",
                    "rulegarden_undo",
                }.issubset({tool.name for tool in tools.tools})

                result = await session.call_tool("rulegarden_initialize", {"project_root": str(tmp_path)})
                assert result.isError is not True

    anyio.run(exercise_server)
    assert (tmp_path / ".rulegarden" / "rules.yaml").is_file()
