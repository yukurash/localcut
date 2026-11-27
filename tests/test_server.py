"""The MCP server starts over stdio and exposes exactly the gated tools."""

import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"footage_status", "get_edit_brief", "submit_edit_plan", "render_preview", "review_render", "egress_report"}


def test_server_lists_tools():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")])
        async with Client(params, read_timeout_seconds=60) as c:
            return {t.name for t in (await c.list_tools()).tools}

    assert asyncio.run(run()) == EXPECTED
