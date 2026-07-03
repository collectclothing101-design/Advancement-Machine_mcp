"""
Workflow Engine — DAG composer with conditional branching, parallel execution,
and MCP tool definitions.

Enables AI agents to define multi-step workflows as directed acyclic graphs
(DAGs) where each node is an MCP tool call, a sub-workflow, or a conditional
branch. The engine resolves dependencies, executes parallel phases, and
handles branching based on prior results.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)

class NodeType(Enum):
    TOOL_CALL = "tool_call"
    SUB_WORKFLOW = "sub_workflow"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    MERGE = "merge"

class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class WorkflowNode:
    def __init__(self, node_id: str, node_type: NodeType,
                 tool_name: str = "", arguments: dict = None,
                 condition: Optional[Callable[[dict], bool]] = None,
                 sub_workflow: Optional['WorkflowDefinition'] = None,
                 dependencies: List[str] = None):
        self.node_id = node_id
        self.node_type = node_type
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.condition = condition
        self.sub_workflow = sub_workflow
        self.dependencies = dependencies or []
        self.status = NodeStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None

class WorkflowDefinition:
    def __init__(self, workflow_id: str, name: str, description: str = ""):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.nodes: Dict[str, WorkflowNode] = {}
        self.entry_points: List[str] = []

    def add_node(self, node: WorkflowNode):
        self.nodes[node.node_id] = node
        if not node.dependencies:
            self.entry_points.append(node.node_id)

class WorkflowEngine:
    """DAG-based workflow composer and executor.

    AI agents can define workflows as sequences of MCP tool calls with
    dependencies, conditional branches, and parallel phases. The engine
    resolves the DAG, executes nodes in dependency order, and returns
    aggregated results.
    """

    def __init__(self):
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self._tool_executor: Optional[Callable[[str, dict], Awaitable[Any]]] = None

    def set_tool_executor(self, executor: Callable[[str, dict], Awaitable[Any]]):
        """Register the function that executes MCP tool calls."""
        self._tool_executor = executor

    def create_workflow(self, name: str, description: str = "") -> WorkflowDefinition:
        """Create a new empty workflow definition."""
        wf_id = hashlib.md5(f"{name}:{uuid.uuid4().hex}".encode()).hexdigest()[:12]
        wf = WorkflowDefinition(wf_id, name, description)
        self.workflows[wf_id] = wf
        return wf

    def add_tool_node(self, workflow_id: str, tool_name: str, arguments: dict = None,
                      dependencies: List[str] = None, node_id: str = "") -> str:
        """Add a tool-call node to a workflow."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        nid = node_id or f"tool_{tool_name}_{len(wf.nodes)}"
        node = WorkflowNode(node_id=nid, node_type=NodeType.TOOL_CALL,
                            tool_name=tool_name, arguments=arguments or {},
                            dependencies=dependencies or [])
        wf.add_node(node)
        return nid

    def add_conditional_node(self, workflow_id: str, condition: Callable[[dict], bool],
                              node_id: str = "", dependencies: List[str] = None) -> str:
        """Add a conditional branch node. The condition function receives the
        accumulated context dict and should return True/False to determine
        which branch executes next."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        nid = node_id or f"cond_{len(wf.nodes)}"
        node = WorkflowNode(node_id=nid, node_type=NodeType.CONDITIONAL,
                            condition=condition, dependencies=dependencies or [])
        wf.add_node(node)
        return nid

    async def execute_workflow(self, workflow_id: str,
                                initial_context: dict = None) -> dict:
        """Execute a workflow DAG.

        Resolves dependencies, runs parallel phases concurrently, evaluates
        conditional branches, and accumulates results into a context dict.
        """
        wf = self.workflows.get(workflow_id)
        if not wf:
            return {"error": f"Workflow {workflow_id} not found"}

        context = initial_context or {}
        all_results = {}
        executed: set = set()
        failed: set = set()

        # Build adjacency for dependency resolution
        remaining = set(wf.nodes.keys())

        while remaining:
            # Find nodes whose dependencies are all satisfied
            ready = []
            for nid in remaining:
                node = wf.nodes[nid]
                deps_met = all(d in executed for d in node.dependencies)
                if deps_met:
                    ready.append(nid)

            if not ready:
                # Deadlock — remaining nodes have unmet dependencies
                for nid in remaining:
                    node = wf.nodes[nid]
                    missing = [d for d in node.dependencies if d not in executed]
                    logger.error(f"Workflow deadlock: node {nid} waiting for {missing}")
                    node.status = NodeStatus.FAILED
                    node.error = f"Deadlock: missing dependencies {missing}"
                    failed.add(nid)
                    remaining.discard(nid)
                continue

            # Execute ready nodes in parallel
            phase_tasks = []
            for nid in ready:
                node = wf.nodes[nid]
                phase_tasks.append(self._execute_node(node, context))

            phase_results = await asyncio.gather(*phase_tasks, return_exceptions=True)

            for nid, result in zip(ready, phase_results):
                node = wf.nodes[nid]
                if isinstance(result, Exception):
                    node.status = NodeStatus.FAILED
                    node.error = str(result)
                    failed.add(nid)
                    all_results[nid] = {"status": "failed", "error": str(result)}
                else:
                    node.status = NodeStatus.COMPLETED
                    node.result = result
                    executed.add(nid)
                    all_results[nid] = {"status": "completed", "result": result}
                    # Update context with result
                    context[nid] = result

                remaining.discard(nid)

        return {
            "workflow_id": workflow_id,
            "name": wf.name,
            "status": "completed" if not failed else "partial_failure",
            "node_count": len(wf.nodes),
            "completed": len(executed),
            "failed": len(failed),
            "results": all_results,
            "context": context,
        }

    async def _execute_node(self, node: WorkflowNode, context: dict) -> Any:
        """Execute a single node based on its type."""
        node.status = NodeStatus.RUNNING

        if node.node_type == NodeType.TOOL_CALL:
            if not self._tool_executor:
                raise RuntimeError("No tool executor registered")
            result = await self._tool_executor(node.tool_name, node.arguments)
            return result

        elif node.node_type == NodeType.CONDITIONAL:
            if not node.condition:
                raise ValueError("Conditional node has no condition function")
            branch_result = node.condition(context)
            return {"branch": branch_result, "condition_met": branch_result}

        elif node.node_type == NodeType.SUB_WORKFLOW:
            if not node.sub_workflow:
                raise ValueError("Sub-workflow node has no sub-workflow")
            return await self.execute_workflow(node.sub_workflow.workflow_id, context)

        else:
            raise ValueError(f"Unknown node type: {node.node_type}")

    def to_json(self, workflow_id: str) -> dict:
        """Serialize a workflow definition to JSON for inspection."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return {"error": "Workflow not found"}
        nodes = []
        for nid, node in wf.nodes.items():
            nodes.append({
                "node_id": nid,
                "type": node.node_type.value,
                "tool_name": node.tool_name,
                "has_condition": node.condition is not None,
                "dependencies": node.dependencies,
                "status": node.status.value,
            })
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "node_count": len(nodes),
            "entry_points": wf.entry_points,
            "nodes": nodes,
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "workflow_create",
                "description": "Create a new workflow definition",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Workflow name"},
                        "description": {"type": "string", "description": "Workflow description"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "workflow_add_tool",
                "description": "Add a tool-call node to a workflow",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object", "default": {}},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "default": []},
                    },
                    "required": ["workflow_id", "tool_name"],
                },
            },
            {
                "name": "workflow_execute",
                "description": "Execute a workflow DAG",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                        "initial_context": {"type": "object", "default": {}},
                    },
                    "required": ["workflow_id"],
                },
            },
            {
                "name": "workflow_status",
                "description": "Get the status of a workflow and its nodes",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string"},
                    },
                    "required": ["workflow_id"],
                },
            },
        ]