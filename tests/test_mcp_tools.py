"""Integration tests for MCP server tool handlers covering success and error paths."""
import json
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["-m", "advancement_machine.mcp_server"],
)

@pytest.mark.asyncio
async def test_force_health_tool_exists():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "advancement_force_health" in names

@pytest.mark.asyncio
async def test_force_health_tool_returns_health():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("advancement_force_health", {})
            text = result.content[0].text
            data = json.loads(text)
            assert "status" in data

@pytest.mark.asyncio
async def test_enhance_payload_missing_argument():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("advancement_enhance_payload", {})
            assert "missing payload_b64" in result.content[0].text

@pytest.mark.asyncio
async def test_enhance_payload_success():
    import base64
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            payload_b64 = base64.b64encode(b"hello").decode()
            result = await session.call_tool("advancement_enhance_payload", {"payload_b64": payload_b64})
            decoded = base64.b64decode(result.content[0].text)
            assert decoded != b"hello"  # transformation applied

@pytest.mark.asyncio
async def test_enhance_payload_timeout_handling():
    import base64
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            payload_b64 = base64.b64encode(b"test").decode()
            result = await session.call_tool("advancement_enhance_payload", {
                "payload_b64": payload_b64,
                "timeout": 0.001
            })
            assert "Error" in result.content[0].text