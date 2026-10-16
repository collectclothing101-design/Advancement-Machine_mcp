"""Workflow graph integrity and adaptation feedback regressions."""

import asyncio

import pytest

from advancement_machine.recursive_improvement import RecursiveImprovementEngine
from advancement_machine.workflow_engine import NodeStatus, NodeType, WorkflowEngine, WorkflowNode


@pytest.mark.asyncio
async def test_parallel_diamond_and_metric_feedback():
    adaptation = RecursiveImprovementEngine()
    engine = WorkflowEngine(improvement_engine=adaptation)
    workflow = engine.create_workflow("diamond")
    arrived = set()
    gate = asyncio.Event()

    async def execute(name, _arguments):
        if name in ("left", "right"):
            arrived.add(name)
            if len(arrived) == 2:
                gate.set()
            await asyncio.wait_for(gate.wait(), timeout=1)
        return name

    engine.set_tool_executor(execute)
    for name, deps in [
        ("root", []),
        ("left", ["root"]),
        ("right", ["root"]),
        ("join", ["left", "right"]),
    ]:
        engine.add_tool_node(workflow.workflow_id, name, node_id=name, dependencies=deps)
    context = {}
    result = await engine.execute_workflow(workflow.workflow_id, context)
    assert result["completed"] == 4
    assert result["context"]["join"] == "join"
    assert context == {}
    assert adaptation.metrics["error_rate"] == [0]
    assert adaptation.metrics["execution_time"][0] > 0
    assert adaptation.metrics["throughput"][0] > 0


@pytest.mark.asyncio
async def test_failure_skips_descendants_and_rerun_resets_state():
    engine = WorkflowEngine()
    workflow = engine.create_workflow("failure")
    calls = []

    async def execute(name, _):
        calls.append(name)
        if name == "bad":
            raise ValueError("broken")
        return name

    engine.set_tool_executor(execute)
    for name, deps in [
        ("bad", []),
        ("blocked", ["bad"]),
        ("descendant", ["blocked"]),
        ("good", []),
    ]:
        engine.add_tool_node(workflow.workflow_id, name, node_id=name, dependencies=deps)
    result = await engine.execute_workflow(workflow.workflow_id)
    assert result["failed"] == 1
    assert result["skipped"] == 2
    assert calls == ["bad", "good"]
    assert workflow.nodes["blocked"].status == NodeStatus.SKIPPED

    async def succeed(name, _):
        return name

    engine.set_tool_executor(succeed)
    assert (await engine.execute_workflow(workflow.workflow_id))["completed"] == 4
    assert all(node.error is None for node in workflow.nodes.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("dependencies", [["missing"], ["node"]])
async def test_invalid_graph_fails_before_tool_side_effects(dependencies):
    engine = WorkflowEngine()
    workflow = engine.create_workflow("invalid")
    engine.add_tool_node(workflow.workflow_id, "noop", node_id="node", dependencies=dependencies)

    async def unexpected(*_):
        pytest.fail("Invalid graphs must not execute tools")

    engine.set_tool_executor(unexpected)
    assert "error" in await engine.execute_workflow(workflow.workflow_id)


def test_duplicate_nodes_are_rejected():
    engine = WorkflowEngine()
    workflow = engine.create_workflow("duplicate")
    engine.add_tool_node(workflow.workflow_id, "noop", node_id="node")
    with pytest.raises(ValueError, match="Duplicate"):
        engine.add_tool_node(workflow.workflow_id, "noop", node_id="node")


@pytest.mark.asyncio
async def test_recursive_subworkflow_fails_and_releases_guard():
    engine = WorkflowEngine()
    workflow = engine.create_workflow("recursive")
    workflow.add_node(WorkflowNode("recursive", NodeType.SUB_WORKFLOW, sub_workflow=workflow))
    for _ in range(2):
        result = await engine.execute_workflow(workflow.workflow_id)
        assert result["failed"] == 1
        assert "recursively referenced" in result["results"]["recursive"]["error"]
