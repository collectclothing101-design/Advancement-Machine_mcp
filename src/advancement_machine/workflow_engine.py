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
import logging
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, Optional

from .recursive_improvement import RecursiveImprovementEngine

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
    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        tool_name: str = "",
        arguments: dict[str, Any] | None = None,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        sub_workflow: Optional["WorkflowDefinition"] = None,
        dependencies: list[str] | None = None,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.condition = condition
        self.sub_workflow = sub_workflow
        self.dependencies = dependencies or []
        self.status = NodeStatus.PENDING
        self.result: Any = None
        self.error: str | None = None


class WorkflowDefinition:
    def __init__(self, workflow_id: str, name: str, description: str = "") -> None:
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.nodes: dict[str, WorkflowNode] = {}
        self.entry_points: list[str] = []

    def add_node(self, node: WorkflowNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node ID: {node.node_id}")
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

    def __init__(self, improvement_engine: RecursiveImprovementEngine | None = None) -> None:
        self.improvement_engine = improvement_engine
        self._active_workflows: set[str] = set()
        self.workflows: dict[str, WorkflowDefinition] = {}
        self._tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None

    def set_tool_executor(self, executor: Callable[[str, dict[str, Any]], Awaitable[Any]]) -> None:
        """Register the function that executes MCP tool calls."""
        self._tool_executor = executor

    def create_workflow(self, name: str, description: str = "") -> WorkflowDefinition:
        """Create a new empty workflow definition."""
        wf_id = hashlib.md5(f"{name}:{uuid.uuid4().hex}".encode()).hexdigest()[:12]
        wf = WorkflowDefinition(wf_id, name, description)
        self.workflows[wf_id] = wf
        return wf

    def add_tool_node(
        self,
        workflow_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        node_id: str = "",
    ) -> str:
        """Add a tool-call node to a workflow."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        nid = node_id or f"tool_{tool_name}_{len(wf.nodes)}"
        node = WorkflowNode(
            node_id=nid,
            node_type=NodeType.TOOL_CALL,
            tool_name=tool_name,
            arguments=arguments or {},
            dependencies=dependencies or [],
        )
        wf.add_node(node)
        return nid

    def add_conditional_node(
        self,
        workflow_id: str,
        condition: Callable[[dict[str, Any]], bool],
        node_id: str = "",
        dependencies: list[str] | None = None,
    ) -> str:
        """Add a conditional branch node. The condition function receives the
        accumulated context dict and should return True/False to determine
        which branch executes next."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")
        nid = node_id or f"cond_{len(wf.nodes)}"
        node = WorkflowNode(
            node_id=nid,
            node_type=NodeType.CONDITIONAL,
            condition=condition,
            dependencies=dependencies or [],
        )
        wf.add_node(node)
        return nid

    async def execute_workflow(
        self, workflow_id: str, initial_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a workflow DAG.

        Resolves dependencies, runs parallel phases concurrently, evaluates
        conditional branches, and accumulates results into a context dict.
        """
        wf = self.workflows.get(workflow_id)
        if not wf:
            return {"error": f"Workflow {workflow_id} not found"}

        if workflow_id in self._active_workflows:
            return {"error": f"Workflow {workflow_id} is already running or recursively referenced"}
        self._active_workflows.add(workflow_id)
        started = time.perf_counter()
        outcome = None
        try:
            outcome = await self._run_workflow(wf, dict(initial_context or {}))
            return outcome
        finally:
            self._active_workflows.discard(workflow_id)
            if self.improvement_engine is not None:
                elapsed = time.perf_counter() - started
                completed = sum(n.status == NodeStatus.COMPLETED for n in wf.nodes.values())
                unsuccessful = sum(
                    n.status in (NodeStatus.FAILED, NodeStatus.SKIPPED) for n in wf.nodes.values()
                )
                self.improvement_engine.record_metric("execution_time", elapsed)
                self.improvement_engine.record_metric(
                    "error_rate",
                    (
                        1.0
                        if outcome is None or "error" in outcome
                        else unsuccessful / max(len(wf.nodes), 1)
                    ),
                )
                self.improvement_engine.record_metric("throughput", completed / max(elapsed, 1e-12))

    async def _run_workflow(
        self, wf: WorkflowDefinition, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve each edge once, with stable ordering and explicit failure propagation."""
        for node in wf.nodes.values():
            node.status, node.result, node.error = NodeStatus.PENDING, None, None
        successors: dict[str, list[str]] = {nid: [] for nid in wf.nodes}
        pending = {}
        for nid, node in wf.nodes.items():
            dependencies = set(node.dependencies)
            missing = dependencies - wf.nodes.keys()
            if missing:
                return {"error": f"Node {nid} has missing dependencies: {sorted(missing)}"}
            pending[nid] = len(dependencies)
            for dependency in sorted(dependencies):
                successors[dependency].append(nid)

        # Validate acyclicity before any tool side effects.
        counts = pending.copy()
        queue = deque(nid for nid, count in counts.items() if count == 0)
        visited = 0
        while queue:
            nid = queue.popleft()
            visited += 1
            for child in successors[nid]:
                counts[child] -= 1
                if counts[child] == 0:
                    queue.append(child)
        if visited != len(wf.nodes):
            return {"error": "Workflow contains a dependency cycle"}

        ready = [nid for nid, count in pending.items() if count == 0]
        results = {}
        while ready:
            runnable = []
            for nid in ready:
                node = wf.nodes[nid]
                if any(wf.nodes[d].status != NodeStatus.COMPLETED for d in node.dependencies):
                    node.status = NodeStatus.SKIPPED
                    node.error = "Dependency did not complete successfully"
                    results[nid] = {"status": "skipped", "error": node.error}
                else:
                    runnable.append(nid)
            phase_results = await asyncio.gather(
                *(self._execute_node(wf.nodes[nid], context.copy()) for nid in runnable),
                return_exceptions=True,
            )
            for nid, result in zip(runnable, phase_results, strict=True):
                node = wf.nodes[nid]
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    node.status, node.error = NodeStatus.FAILED, str(result)
                    results[nid] = {"status": "failed", "error": str(result)}
                else:
                    node.status, node.result = NodeStatus.COMPLETED, result
                    results[nid] = {"status": "completed", "result": result}
                    context[nid] = result
            next_ready = []
            for nid in ready:
                for child in successors[nid]:
                    pending[child] -= 1
                    if pending[child] == 0:
                        next_ready.append(child)
            ready = next_ready

        completed = sum(n.status == NodeStatus.COMPLETED for n in wf.nodes.values())
        failed = sum(n.status == NodeStatus.FAILED for n in wf.nodes.values())
        skipped = sum(n.status == NodeStatus.SKIPPED for n in wf.nodes.values())
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "status": "partial_failure" if failed or skipped else "completed",
            "node_count": len(wf.nodes),
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "results": results,
            "context": context,
        }

    async def _execute_node(self, node: WorkflowNode, context: dict[str, Any]) -> Any:
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
            result = await self.execute_workflow(node.sub_workflow.workflow_id, context)
            if result.get("error") or result.get("status") != "completed":
                raise RuntimeError(f"Sub-workflow failed: {result}")
            return result

        else:
            raise ValueError(f"Unknown node type: {node.node_type}")

    def to_json(self, workflow_id: str) -> dict[str, Any]:
        """Serialize a workflow definition to JSON for inspection."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return {"error": "Workflow not found"}
        nodes = []
        for nid, node in wf.nodes.items():
            nodes.append(
                {
                    "node_id": nid,
                    "type": node.node_type.value,
                    "tool_name": node.tool_name,
                    "has_condition": node.condition is not None,
                    "dependencies": node.dependencies,
                    "status": node.status.value,
                }
            )
        return {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "node_count": len(nodes),
            "entry_points": wf.entry_points,
            "nodes": nodes,
        }

    def get_tool_definitions(self) -> list[dict[str, Any]]:
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
                        "dependencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                        },
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
