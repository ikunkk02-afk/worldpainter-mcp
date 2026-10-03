from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "worldpainter_mcp"])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            assert len(names) == 8, names
            print("MCP handshake OK:", ", ".join(names))


if __name__ == "__main__":
    asyncio.run(main())
