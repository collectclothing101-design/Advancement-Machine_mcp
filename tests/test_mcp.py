"""Integration tests for MCP server using MCP client."""
import json
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["-m", "advancement_machine.mcp_server"],
)

@pytest.mark.asyncio
async def test_mcp_tools():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "advancement_doctor" in names
            assert "advancement_config" in names
            assert "advancement_force_health" in names
            assert "advancement_enhance_payload" in names

@pytest.mark.asyncio
async def test_mcp_call_doctor():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("advancement_doctor", {})
            text = result.content[0].text
            data = json.loads(text)
            assert data["app"] == "Advancement Machine"
            assert data["healthy"] is True

@pytest.mark.asyncio
async def test_mcp_config():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("advancement_config", {})
            text = result.content[0].text
            assert "log_level" in text

@pytest.mark.asyncio
async def test_mcp_force_health():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("advancement_force_health", {})
            text = result.content[0].text
            data = json.loads(text)
            assert "status" in data

@pytest.mark.asyncio
async def test_mcp_enhance_payload():
    import base64
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            payload_b64 = base64.b64encode(b"hello").decode()
            result = await session.call_tool("advancement_enhance_payload", {"payload_b64": payload_b64})
            decoded = base64.b64decode(result.content[0].text)
            assert decoded != b"hello"

@pytest.mark.asyncio
async def test_mcp_resources():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resources = await session.list_resources()
            uris = [r.uri for r in resources.resources]
            assert "advancement://config" in uris
            assert "advancement://doctor" in uris

@pytest.mark.asyncio
async def test_mcp_prompts():
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            prompts = await session.list_prompts()
            names = [p.name for p in prompts.prompts]
            assert "advancement_assess" in names