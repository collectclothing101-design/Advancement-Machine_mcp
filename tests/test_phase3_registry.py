"""
Tests for Phase 3: Function Registry & Smart Dispatch.

Tests:
  1. Schema generation from handlers
  2. Task discovery and registration
  3. Task execution with validation
  4. Batch execution
  5. MCP tool export
  6. Metrics aggregation
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from advancement_machine.intel_mcp.task_framework import (
    TaskContext,
    TaskResult,
    TaskStatus,
    TaskMetrics,
    task_handler,
)
from advancement_machine.intel_mcp.gitmcp_registry import (
    TaskSchemaParameter,
    TaskSchema,
    generate_schema_from_handler,
    GitMCPRegistry,
    get_global_registry,
    reset_global_registry,
)


# ═════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════

@pytest.fixture
def registry():
    """Create a registry for testing."""
    return GitMCPRegistry()


@pytest.fixture
def task_context():
    """Create a TaskContext for testing."""
    return TaskContext(task_name="test_task")


# ═════════════════════════════════════════════════════════════════════════
# Tests: Schema Generation
# ═════════════════════════════════════════════════════════════════════════

class TestSchemaGeneration:
    """Test schema generation from handlers."""

    def test_schema_parameter_to_dict(self):
        """Test parameter serialization."""
        param = TaskSchemaParameter(
            name="gist_id",
            type_name="str",
            required=True,
            description="GitHub gist ID"
        )
        d = param.to_dict()
        
        assert d["name"] == "gist_id"
        assert d["type"] == "str"
        assert d["required"] is True
        assert d["description"] == "GitHub gist ID"

    def test_task_schema_to_dict(self):
        """Test schema serialization."""
        schema = TaskSchema(
            name="gist:fetch_raw",
            description="Fetch gist from API",
            parameters=[
                TaskSchemaParameter("gist_id", "str", required=True),
            ],
            tags=["gist", "fetch"]
        )
        d = schema.to_dict()
        
        assert d["name"] == "gist:fetch_raw"
        assert d["description"] == "Fetch gist from API"
        assert len(d["parameters"]) == 1
        assert len(d["tags"]) == 2

    def test_task_schema_to_mcp_tool(self):
        """Test MCP tool format conversion."""
        schema = TaskSchema(
            name="gist:fetch_raw",
            description="Fetch gist",
            parameters=[
                TaskSchemaParameter("gist_id", "str", required=True),
                TaskSchemaParameter("timeout", "int", required=False, default=30),
            ]
        )
        tool = schema.to_mcp_tool()
        
        assert tool["name"] == "gist:fetch_raw"
        assert "gist_id" in tool["inputSchema"]["properties"]
        assert "timeout" in tool["inputSchema"]["properties"]
        assert "gist_id" in tool["inputSchema"]["required"]
        assert "timeout" not in tool["inputSchema"]["required"]

    def test_generate_schema_from_handler(self):
        """Test auto-generating schema from handler."""
        @task_handler(name="test:demo")
        async def demo_handler(context: TaskContext, value: str, count: int = 5) -> TaskResult:
            """Demo handler for testing."""
            return TaskResult.success(data={"value": value, "count": count})
        
        schema = generate_schema_from_handler("test:demo", demo_handler)
        
        assert schema.name == "test:demo"
        assert "testing" in schema.description.lower() or "Demo" in schema.description
        assert len(schema.parameters) == 2
        
        # Find parameters
        value_param = next((p for p in schema.parameters if p.name == "value"), None)
        count_param = next((p for p in schema.parameters if p.name == "count"), None)
        
        assert value_param is not None
        assert value_param.required is True
        assert count_param is not None
        assert count_param.required is False

    def test_python_type_to_json_type(self):
        """Test Python type conversion."""
        assert TaskSchema._python_type_to_json_type("str") == "string"
        assert TaskSchema._python_type_to_json_type("int") == "integer"
        assert TaskSchema._python_type_to_json_type("float") == "number"
        assert TaskSchema._python_type_to_json_type("bool") == "boolean"
        assert TaskSchema._python_type_to_json_type("list") == "array"
        assert TaskSchema._python_type_to_json_type("dict") == "object"


# ═════════════════════════════════════════════════════════════════════════
# Tests: Registry Operations
# ═════════════════════════════════════════════════════════════════════════

class TestGitMCPRegistry:
    """Test GitMCPRegistry."""

    @pytest.mark.asyncio
    async def test_registry_initialization(self, registry):
        """Test registry creation."""
        assert registry.tasks == {}
        assert registry.schemas == {}
        assert isinstance(registry.metrics, TaskMetrics)
        assert registry.execution_log == []

    @pytest.mark.asyncio
    async def test_discover_tasks(self, registry):
        """Test task discovery."""
        count = await registry.discover_tasks()
        
        # Should discover at least one task (the test:demo from earlier or built-in gist tasks)
        assert count >= 1
        assert len(registry.tasks) == count
        assert len(registry.schemas) == count
        # Check that tasks were actually registered
        assert len(registry.tasks) > 0

    @pytest.mark.asyncio
    async def test_get_task(self, registry):
        """Test getting task by name."""
        await registry.discover_tasks()
        
        # Get any task that was discovered
        if registry.tasks:
            task_name = list(registry.tasks.keys())[0]
            handler = registry.get_task(task_name)
            assert handler is not None
            assert callable(handler)

    @pytest.mark.asyncio
    async def test_get_schema(self, registry):
        """Test getting schema by name."""
        await registry.discover_tasks()
        
        # Get any schema that was discovered
        if registry.schemas:
            schema_name = list(registry.schemas.keys())[0]
            schema = registry.get_schema(schema_name)
            assert schema is not None
            assert schema.name == schema_name

    @pytest.mark.asyncio
    async def test_list_tasks(self, registry):
        """Test listing all tasks."""
        await registry.discover_tasks()
        
        tasks = registry.list_tasks()
        assert isinstance(tasks, list)
        assert len(tasks) > 0  # Should have discovered at least one task

    def test_list_schemas(self, registry):
        """Test listing all schemas."""
        # Manually add a schema for testing
        schema = TaskSchema(name="test:dummy")
        registry.schemas["test:dummy"] = schema
        
        schemas = registry.list_schemas()
        assert "test:dummy" in schemas
        assert schemas["test:dummy"] == schema

    def test_to_mcp_tools(self, registry):
        """Test MCP tool export."""
        schema1 = TaskSchema(name="test:task1", description="Task 1")
        schema2 = TaskSchema(name="test:task2", description="Task 2")
        registry.schemas["test:task1"] = schema1
        registry.schemas["test:task2"] = schema2
        
        tools = registry.to_mcp_tools()
        
        assert len(tools) == 2
        assert any(t["name"] == "test:task1" for t in tools)
        assert any(t["name"] == "test:task2" for t in tools)

    @pytest.mark.asyncio
    async def test_execute_success(self, registry, task_context):
        """Test successful task execution."""
        # Register a mock task
        async def mock_task(context: TaskContext, value: str) -> TaskResult:
            return TaskResult.success({"result": value})
        
        registry.tasks["test:mock"] = mock_task
        registry.schemas["test:mock"] = TaskSchema(
            name="test:mock",
            parameters=[TaskSchemaParameter("value", "str", required=True)]
        )
        
        result = await registry.execute("test:mock", task_context, value="hello")
        
        assert result.is_success()
        assert result.data == {"result": "hello"}
        assert registry.metrics.counters.get("registry.execution.success", 0) > 0

    @pytest.mark.asyncio
    async def test_execute_not_found(self, registry, task_context):
        """Test executing non-existent task."""
        result = await registry.execute("test:nonexistent", task_context)
        
        assert result.is_error()
        assert "not found" in (result.error_info or {}).get("message", "").lower()
        assert registry.metrics.counters.get("registry.execution.not_found", 0) > 0

    @pytest.mark.asyncio
    async def test_validate_inputs_required(self, registry, task_context):
        """Test input validation for required params."""
        schema = TaskSchema(
            name="test:task",
            parameters=[TaskSchemaParameter("gist_id", "str", required=True)]
        )
        
        # Should raise on missing required param
        with pytest.raises(Exception):  # TaskValidationError
            registry._validate_inputs("test:task", schema, {})

    @pytest.mark.asyncio
    async def test_validate_inputs_optional(self, registry, task_context):
        """Test input validation for optional params."""
        schema = TaskSchema(
            name="test:task",
            parameters=[TaskSchemaParameter("timeout", "int", required=False)]
        )
        
        # Should NOT raise if optional param missing
        try:
            registry._validate_inputs("test:task", schema, {})
        except Exception:
            pytest.fail("Should not raise for optional parameters")

    @pytest.mark.asyncio
    async def test_execute_batch(self, registry):
        """Test batch execution."""
        # Register mock task
        async def mock_task(context: TaskContext, value: str) -> TaskResult:
            return TaskResult.success({"result": value})
        
        registry.tasks["test:mock"] = mock_task
        registry.schemas["test:mock"] = TaskSchema(
            name="test:mock",
            parameters=[TaskSchemaParameter("value", "str", required=True)]
        )
        
        items = [
            {"value": "a"},
            {"value": "b"},
            {"value": "c"},
        ]
        
        results = await registry.execute_batch("test:mock", items)
        
        assert len(results) == 3
        assert all(r.is_success() for r in results)
        assert results[0].data == {"result": "a"}
        assert results[1].data == {"result": "b"}
        assert results[2].data == {"result": "c"}

    def test_get_metrics_summary(self, registry):
        """Test metrics summary."""
        registry.tasks["test:task1"] = lambda: None
        registry.schemas["test:task1"] = TaskSchema(name="test:task1")
        registry.metrics.inc("test.counter", 5)
        
        summary = registry.get_metrics_summary()
        
        assert summary["tasks_registered"] == 1
        assert summary["registry"]["counters"].get("test.counter") == 5
        assert "timestamp" in summary

    def test_get_execution_log(self, registry):
        """Test execution log retrieval."""
        registry.execution_log = [
            {"task": "task1", "status": "complete", "duration_ms": 100},
            {"task": "task2", "status": "complete", "duration_ms": 150},
            {"task": "task1", "status": "complete", "duration_ms": 120},
        ]
        
        all_logs = registry.get_execution_log()
        assert len(all_logs) == 3
        
        task1_logs = registry.get_execution_log(task_name="task1")
        assert len(task1_logs) == 2
        assert all(log["task"] == "task1" for log in task1_logs)

    def test_clear_execution_log(self, registry):
        """Test clearing execution log."""
        registry.execution_log = [{"task": "test"}]
        assert len(registry.execution_log) == 1
        
        registry.clear_execution_log()
        assert len(registry.execution_log) == 0


# ═════════════════════════════════════════════════════════════════════════
# Tests: Global Registry
# ═════════════════════════════════════════════════════════════════════════

class TestGlobalRegistry:
    """Test global registry singleton."""

    @pytest.mark.asyncio
    async def test_get_global_registry(self):
        """Test getting global registry."""
        await reset_global_registry()
        
        reg1 = await get_global_registry()
        reg2 = await get_global_registry()
        
        # Should be same instance
        assert reg1 is reg2
        assert len(reg1.tasks) > 0  # Should be populated after discovery

    @pytest.mark.asyncio
    async def test_reset_global_registry(self):
        """Test resetting global registry."""
        # Create one
        reg1 = await get_global_registry()
        assert len(reg1.tasks) > 0
        
        # Reset
        await reset_global_registry()
        
        # Create new one
        reg2 = await get_global_registry()
        assert reg1 is not reg2
        assert len(reg2.tasks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
