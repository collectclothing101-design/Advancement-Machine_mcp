"""Test plugin loading, hook registration, and agent route discovery."""
import pytest
from advancement_machine.plugin_loader import PluginManager

@pytest.fixture
def plugin_dir(tmp_path):
    plugin_code = """
from advancement_machine.plugin_hooks import mcp_tool, mcp_resource, agent_route

@mcp_tool(name="test_tool", description="A test tool", input_schema={})
async def test_tool(args):
    return {"result": "ok"}

@mcp_resource(uri="test://resource", name="Test Resource", description="Resource for testing")
async def test_resource():
    return '{"res": "data"}'

@agent_route(agent_name="tester", description="Test agent", keywords=["test", "demo"])
async def test_agent(intent, context):
    return {"agent": "tester", "response": "handled"}
"""
    plugin_file = tmp_path / "test_plugin.py"
    plugin_file.write_text(plugin_code)
    return tmp_path

@pytest.mark.asyncio
async def test_plugin_loading(plugin_dir):
    mgr = PluginManager(str(plugin_dir), hot_reload=False)
    assert len(mgr.all()) == 1
    plugin = mgr.get("test_plugin")
    assert plugin is not None
    hooks = plugin.get_hooks("mcp_tool")
    assert len(hooks) == 1
    assert hooks[0].tool_def.name == "test_tool"

@pytest.mark.asyncio
async def test_plugin_hook_trigger(plugin_dir):
    mgr = PluginManager(str(plugin_dir), hot_reload=False)
    plugin = mgr.get("test_plugin")
    hook = plugin.get_hooks("mcp_tool")[0]
    result = await hook.fn({})
    assert result["result"] == "ok"

@pytest.mark.asyncio
async def test_agent_route_discovery(plugin_dir):
    from advancement_machine.agent_orchestrator import AgentOrchestrator
    mgr = PluginManager(str(plugin_dir), hot_reload=False)
    orch = AgentOrchestrator(mgr)
    agents = orch.list_agents()
    names = [a["name"] for a in agents]
    assert "tester" in names

@pytest.mark.asyncio
async def test_mcp_resource_hook(plugin_dir):
    mgr = PluginManager(str(plugin_dir), hot_reload=False)
    plugin = mgr.get("test_plugin")
    hooks = plugin.get_hooks("mcp_resource")
    assert len(hooks) == 1
    assert hooks[0].resource_def["uri"] == "test://resource"