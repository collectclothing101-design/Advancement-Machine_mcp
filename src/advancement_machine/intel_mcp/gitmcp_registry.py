"""
GitMCP Function Registry: Centralized task dispatch with auto-schema generation.

This module provides:
  - GitMCPRegistry: Single source of truth for executable functions
  - Auto-schema generation from task handlers
  - Intelligent routing with input validation
  - Unified error handling & standardization
  - MCP tool export (auto-documenting)
  - Task execution metrics aggregation

Design Principle:
  One registry = one registry = truth -> no scattered function definitions
  Schemas auto-generated -> no manual MCP spec maintenance
  Consistent error handling -> every task behaves predictably
  Metrics tracked globally -> system observability


Usage:

  registry = GitMCPRegistry()
  
  # Tasks auto-discovered from _TASK_REGISTRY
  await registry.discover_tasks()
  
  # Execute with validation
  result = await registry.execute("gist:fetch_raw", context, gist_id="123")
  
  # Export as MCP tools
  mcp_tools = registry.to_mcp_tools()
  
  # Monitor performance
  summary = registry.get_metrics_summary()
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type, Union, get_type_hints

from .task_framework import (
    TaskContext,
    TaskResult,
    TaskStatus,
    TaskError,
    TaskValidationError,
    get_task_handler,
    get_all_tasks,
    get_task_schema,
    TaskMetrics,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Schema Generation
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class TaskSchemaParameter:
    """Represents a task parameter in the schema."""
    name: str
    type_name: str
    required: bool = True
    description: str = ""
    default: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-compatible dict."""
        d = {
            "name": self.name,
            "type": self.type_name,
            "required": self.required,
        }
        if self.description:
            d["description"] = self.description
        if self.default is not None:
            d["default"] = self.default
        return d


@dataclass
class TaskSchema:
    """Complete schema for a task (MCP-compatible)."""
    name: str
    description: str = ""
    parameters: List[TaskSchemaParameter] = field(default_factory=list)
    return_type: str = "TaskResult"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-compatible dict."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "return_type": self.return_type,
            "tags": self.tags,
        }

    def to_mcp_tool(self) -> Dict[str, Any]:
        """Convert to MCP tool format."""
        params_dict = {}
        required = []
        
        for param in self.parameters:
            params_dict[param.name] = {
                "type": self._python_type_to_json_type(param.type_name),
                "description": param.description or f"Parameter {param.name}",
            }
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": params_dict,
                "required": required,
            }
        }

    @staticmethod
    def _python_type_to_json_type(python_type: str) -> str:
        """Convert Python type hint to JSON schema type."""
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "dict": "object",
            "list": "array",
            "Dict": "object",
            "List": "array",
        }
        
        # Handle Optional[T] -> T (assume not required)
        if "Optional" in python_type or python_type.startswith("None"):
            python_type = python_type.replace("Optional[", "").replace("]", "")
        
        for py_type, json_type in type_map.items():
            if py_type in python_type:
                return json_type
        
        return "object"  # Default fallback


def generate_schema_from_handler(
    task_name: str,
    handler: Callable,
) -> TaskSchema:
    """Generate schema from a task handler function.
    
    Args:
        task_name: Name of the task
        handler: Async callable with signature (context: TaskContext, **kwargs)
    
    Returns:
        TaskSchema with auto-extracted parameters and types
    """
    # Get function signature
    sig = inspect.signature(handler)
    type_hints = get_type_hints(handler)
    
    # Extract docstring
    docstring = inspect.getdoc(handler) or ""
    description = docstring.split("\n")[0] if docstring else f"Task {task_name}"
    
    # Extract parameters (skip 'context')
    parameters = []
    for param_name, param in sig.parameters.items():
        if param_name == "context":
            continue  # Skip TaskContext param
        
        # Get type hint
        param_type = type_hints.get(param_name, inspect.Parameter.empty)
        type_name = (
            param_type.__name__
            if hasattr(param_type, "__name__")
            else str(param_type)
        )
        
        # Check if required
        required = param.default == inspect.Parameter.empty
        
        parameters.append(TaskSchemaParameter(
            name=param_name,
            type_name=type_name,
            required=required,
            description=f"Parameter {param_name}",
            default=param.default if not required else None,
        ))
    
    return TaskSchema(
        name=task_name,
        description=description,
        parameters=parameters,
        tags=_extract_tags_from_name(task_name),
    )


def _extract_tags_from_name(task_name: str) -> List[str]:
    """Extract tags from task name (e.g., 'gist:fetch_raw' -> ['gist', 'fetch'])."""
    parts = task_name.replace(":", "_").split("_")
    return [p for p in parts if p and p != "raw"]


# ═════════════════════════════════════════════════════════════════════════
# Function Registry
# ═════════════════════════════════════════════════════════════════════════

class GitMCPRegistry:
    """Central registry for all executable functions in GitMCP.
    
    Responsibilities:
      - Discover and register all task handlers
      - Generate schemas for each task
      - Execute tasks with validation
      - Track metrics across all tasks
      - Export as MCP tools
    """

    def __init__(self):
        """Initialize empty registry."""
        self.tasks: Dict[str, Callable] = {}
        self.schemas: Dict[str, TaskSchema] = {}
        self.metrics = TaskMetrics()
        self.execution_log: List[Dict[str, Any]] = []
        logger.info("GitMCPRegistry initialized")

    async def discover_tasks(self) -> int:
        """Discover all registered task handlers from task_framework.
        
        Returns:
            Number of tasks discovered
        """
        all_tasks = get_all_tasks()
        
        for task_name, handler in all_tasks.items():
            try:
                schema = generate_schema_from_handler(task_name, handler)
                self.tasks[task_name] = handler
                self.schemas[task_name] = schema
                logger.info(f"Discovered task: {task_name}")
            except Exception as e:
                logger.error(f"Failed to discover task {task_name}: {e}")
                continue
        
        count = len(self.tasks)
        logger.info(f"Task discovery complete: {count} tasks registered")
        self.metrics.inc("registry.tasks_discovered", count)
        return count

    async def execute(
        self,
        task_name: str,
        context: TaskContext,
        **kwargs: Any,
    ) -> TaskResult:
        """Execute a task with validation and error handling.
        
        Args:
            task_name: Name of task to execute
            context: TaskContext for execution
            **kwargs: Task-specific arguments
        
        Returns:
            TaskResult with status, data, and error_info
        """
        start_time = datetime.now(timezone.utc)
        context.task_name = task_name
        
        try:
            # Check if task exists
            if task_name not in self.tasks:
                self.metrics.inc("registry.execution.not_found")
                raise TaskError(f"Task not found: {task_name}")
            
            handler = self.tasks[task_name]
            schema = self.schemas[task_name]
            
            # Validate inputs against schema
            self._validate_inputs(task_name, schema, kwargs)
            
            # Execute
            self.metrics.inc("registry.execution.started")
            result = await handler(context, **kwargs)
            
            # Record metric
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self.metrics.record_timing(f"registry.task.{task_name}", elapsed_ms)
            
            if result.is_success():
                self.metrics.inc("registry.execution.success")
            elif result.is_error():
                self.metrics.inc("registry.execution.failed")
            elif result.is_retry():
                self.metrics.inc("registry.execution.retry")
            
            # Log execution
            self.execution_log.append({
                "task": task_name,
                "status": result.status.value,
                "duration_ms": elapsed_ms,
                "timestamp": start_time.isoformat(),
            })
            
            return result
        
        except TaskValidationError as e:
            self.metrics.inc("registry.execution.validation_error")
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.warning(f"Validation error in {task_name}: {e}")
            return TaskResult.error(
                e,
                metadata={"task": task_name, "duration_ms": elapsed_ms}
            )
        
        except Exception as e:
            self.metrics.inc("registry.execution.error")
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.error(f"Execution error in {task_name}: {e}")
            return TaskResult.error(
                TaskError(str(e)),
                metadata={"task": task_name, "duration_ms": elapsed_ms}
            )

    def _validate_inputs(
        self,
        task_name: str,
        schema: TaskSchema,
        kwargs: Dict[str, Any],
    ) -> None:
        """Validate inputs against schema.
        
        Args:
            task_name: Task name (for error messages)
            schema: Task schema
            kwargs: Input arguments
        
        Raises:
            TaskValidationError: If validation fails
        """
        # Check required parameters
        for param in schema.parameters:
            if param.required and param.name not in kwargs:
                raise TaskValidationError(
                    f"Missing required parameter: {param.name}",
                    details={
                        "task": task_name,
                        "missing_param": param.name,
                        "required_params": [p.name for p in schema.parameters if p.required],
                    }
                )
        
        # Check type compatibility (basic)
        for param in schema.parameters:
            if param.name in kwargs:
                value = kwargs[param.name]
                # Simple type check (could be enhanced)
                if param.type_name in ["int", "float", "str", "bool"]:
                    expected_type = eval(param.type_name) if param.type_name != "float" else float
                    if not isinstance(value, expected_type):
                        logger.warning(
                            f"Type mismatch for {task_name}.{param.name}: "
                            f"expected {param.type_name}, got {type(value).__name__}"
                        )

    async def execute_batch(
        self,
        task_name: str,
        items: List[Dict[str, Any]],
        context_factory: Optional[Callable[[], TaskContext]] = None,
    ) -> List[TaskResult]:
        """Execute same task on batch of items.
        
        Args:
            task_name: Name of task to execute
            items: List of kwargs dicts
            context_factory: Factory for creating TaskContexts
        
        Returns:
            List of TaskResults
        """
        if not context_factory:
            context_factory = lambda: TaskContext(task_name=task_name)
        
        tasks = []
        for item in items:
            context = context_factory()
            tasks.append(self.execute(task_name, context, **item))
        
        results = await asyncio.gather(*tasks)
        self.metrics.inc("registry.batch.executed", len(items))
        return results

    def get_task(self, task_name: str) -> Optional[Callable]:
        """Get task handler by name."""
        return self.tasks.get(task_name)

    def get_schema(self, task_name: str) -> Optional[TaskSchema]:
        """Get task schema by name."""
        return self.schemas.get(task_name)

    def list_tasks(self) -> List[str]:
        """List all registered task names."""
        return list(self.tasks.keys())

    def list_schemas(self) -> Dict[str, TaskSchema]:
        """List all task schemas."""
        return dict(self.schemas)

    def to_mcp_tools(self) -> List[Dict[str, Any]]:
        """Export all tasks as MCP tools.
        
        Returns:
            List of MCP tool dicts (ready for MCPServer.add_tool)
        """
        return [schema.to_mcp_tool() for schema in self.schemas.values()]

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get aggregated metrics summary."""
        return {
            "registry": self.metrics.get_summary(),
            "tasks_registered": len(self.tasks),
            "execution_log_size": len(self.execution_log),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_execution_log(
        self,
        task_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get execution log, optionally filtered by task.
        
        Args:
            task_name: Filter by task name (None = all)
            limit: Max entries to return
        
        Returns:
            List of execution log entries
        """
        log = self.execution_log
        if task_name:
            log = [e for e in log if e["task"] == task_name]
        return log[-limit:]

    def clear_execution_log(self) -> None:
        """Clear execution log."""
        self.execution_log.clear()


# ═════════════════════════════════════════════════════════════════════════
# Registry Singleton (Global Registry)
# ═════════════════════════════════════════════════════════════════════════

_GLOBAL_REGISTRY: Optional[GitMCPRegistry] = None


async def get_global_registry() -> GitMCPRegistry:
    """Get or create global registry."""
    global _GLOBAL_REGISTRY
    
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = GitMCPRegistry()
        await _GLOBAL_REGISTRY.discover_tasks()
    
    return _GLOBAL_REGISTRY


async def reset_global_registry() -> None:
    """Reset global registry (mainly for testing)."""
    global _GLOBAL_REGISTRY
    _GLOBAL_REGISTRY = None


__all__ = [
    "TaskSchemaParameter",
    "TaskSchema",
    "generate_schema_from_handler",
    "GitMCPRegistry",
    "get_global_registry",
    "reset_global_registry",
]
