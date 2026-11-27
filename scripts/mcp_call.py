"""Call one localcut MCP tool over the real stdio path and print the result.

    python scripts/mcp_call.py get_edit_brief
    python scripts/mcp_call.py submit_edit_plan plan_json=@plan.json

Useful for testing the server without a chat client. `key=@file` reads the value from a file.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def _args(pairs: list[str]) -> dict:
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        if v.startswith("@"):
            v = Path(v[1:]).read_text(encoding="utf-8")
        out[k] = int(v) if v.isdigit() else v
    return out


async def main(tool: str, args: dict) -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")])
    async with Client(params, read_timeout_seconds=1800) as c:
        res = await c.call_tool(tool, args)
        sys.stdout.reconfigure(encoding="utf-8")
        print("".join(getattr(x, "text", "") for x in res.content))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], _args(sys.argv[2:])))
