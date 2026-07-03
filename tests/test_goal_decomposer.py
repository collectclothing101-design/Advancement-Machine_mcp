"""
pytest test suites for GoalDecomposer.decompose covering research, execution,
report, and mixed intents with a mock AgentOrchestrator.

Tests verify sub-goal count, assigned phases, dependency chains, parallel
phase identification, and agent assignment under every intent combination.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from advancement_machine.force_multiplier import GoalDecomposer, SubGoal

# ---------- Fixtures ----------

@pytest.fixture
def mock_orchestrator():
    """Create a mock AgentOrchestrator with a route() that returns named agents.

    The mock's route() method returns an AgentRoute-like object for any intent
    containing a known agent keyword, or None if no keyword matches.
    """
    orch = MagicMock()
    orch.name = "mock_orchestrator"

    # Simulate route() — returns an object with .agent_name if keywords match
    async def fake_route(intent: str):
        intent_lower = intent.lower()
        if "research" in intent_lower or "find" in intent_lower or "search" in intent_lower:
            return MagicMock(agent_name="researcher")
        elif "execute" in intent_lower or "build" in intent_lower or "deploy" in intent_lower:
            return MagicMock(agent_name="executor")
        elif "report" in intent_lower or "summarize" in intent_lower or "document" in intent_lower:
            return MagicMock(agent_name="reporter")
        return None

    orch.route = fake_route
    # store_memory doesn't need to do anything real for these tests
    orch.store_memory = AsyncMock()
    return orch

@pytest.fixture
def decomposer(mock_orchestrator):
    """Return a GoalDecomposer wired to the mock orchestrator."""
    return GoalDecomposer(orchestrator=mock_orchestrator)

# ==============================================================
# RESEARCH INTENT
# ==============================================================

class TestResearchIntent:
    """Intents containing research-type keywords produce a research sub-goal."""

    @pytest.mark.parametrize("intent", [
        "find the latest CVE for log4j",
        "search for open ports on the target",
        "research authentication bypass techniques",
        "investigate the network topology",
        "analyze the traffic patterns",
        "assess the security posture",
    ])
    @pytest.mark.asyncio
    async def test_research_keyword_produces_research_goal(self, decomposer, intent):
        result = await decomposer.decompose(intent)
        sub_goals = result["sub_goals"]
        assert len(sub_goals) >= 1
        research_sg = [sg for sg in sub_goals if "_research" in sg["id"]]
        assert len(research_sg) == 1, f"Expected 1 research sub-goal, got {len(research_sg)}"
        assert research_sg[0]["assigned_agent"] == "researcher"

    @pytest.mark.asyncio
    async def test_research_only_no_extra_goals(self, decomposer):
        """A pure research intent should produce exactly 1 sub-goal."""
        result = await decomposer.decompose("find vulnerabilities")
        assert len(result["sub_goals"]) == 1
        assert result["estimated_complexity"] == 1

    @pytest.mark.asyncio
    async def test_research_has_no_dependencies(self, decomposer):
        """Research sub-goals are always in the first (parallel) phase."""
        result = await decomposer.decompose("research the api surface")
        sg = result["sub_goals"][0]
        assert sg["dependencies"] == []
        assert result["parallel_phases"][0] == [sg["id"]]

# ==============================================================
# EXECUTION INTENT
# ==============================================================

class TestExecutionIntent:
    """Intents containing execution-type keywords produce an execution sub-goal."""

    @pytest.mark.parametrize("intent", [
        "run the exploit module",
        "execute the payload on the target",
        "deploy the beacon to the endpoint",
        "configure the firewall rules",
        "build the container image",
        "create the persistence mechanism",
        "install the agent on the host",
        "compile the kernel module",
    ])
    @pytest.mark.asyncio
    async def test_execution_keyword_produces_execution_goal(self, decomposer, intent):
        result = await decomposer.decompose(intent)
        exec_sg = [sg for sg in result["sub_goals"] if "_execute" in sg["id"]]
        assert len(exec_sg) == 1, f"Expected 1 execution sub-goal, got {len(exec_sg)}"
        assert exec_sg[0]["assigned_agent"] == "executor"

    @pytest.mark.asyncio
    async def test_execution_only_no_extra_goals(self, decomposer):
        result = await decomposer.decompose("run the scanner")
        assert len(result["sub_goals"]) == 1

    @pytest.mark.asyncio
    async def test_execution_has_no_dependencies_when_alone(self, decomposer):
        """Execution alone has no dependencies."""
        result = await decomposer.decompose("build the package")
        sg = result["sub_goals"][0]
        assert sg["dependencies"] == []

# ==============================================================
# REPORT INTENT
# ==============================================================

class TestReportIntent:
    """Intents containing report-type keywords produce a report sub-goal."""

    @pytest.mark.parametrize("intent", [
        "report the findings to the client",
        "summarize the attack chain",
        "document the procedures used",
        "explain the vulnerability impact",
        "describe the exploitation steps",
        "output the results in JSON format",
    ])
    @pytest.mark.asyncio
    async def test_report_keyword_produces_report_goal(self, decomposer, intent):
        result = await decomposer.decompose(intent)
        report_sg = [sg for sg in result["sub_goals"] if "_report" in sg["id"]]
        assert len(report_sg) == 1, f"Expected 1 report sub-goal, got {len(report_sg)}"
        assert report_sg[0]["assigned_agent"] == "reporter"

    @pytest.mark.asyncio
    async def test_report_only_no_extra_goals(self, decomposer):
        result = await decomposer.decompose("report the status")
        assert len(result["sub_goals"]) == 1

    @pytest.mark.asyncio
    async def test_report_has_no_dependencies_when_alone(self, decomposer):
        result = await decomposer.decompose("document the process")
        sg = result["sub_goals"][0]
        assert sg["dependencies"] == []

# ==============================================================
# MIXED INTENTS
# ==============================================================

class TestMixedIntents:
    """Intents combining two or more action types produce multiple sub-goals
    with correct dependency chains."""

    @pytest.mark.parametrize("intent, expected_goal_types", [
        ("research and execute the exploit", {"research", "execute"}),
        ("find the vulnerability then build the payload", {"research", "execute"}),
        ("research and report the findings", {"research", "report"}),
        ("execute the attack and document it", {"execute", "report"}),
        ("assess, exploit, and report", {"research", "execute", "report"}),
        ("research, build, deploy, and summarize", {"research", "execute", "report"}),
    ])
    @pytest.mark.asyncio
    async def test_mixed_intent_produces_correct_subgoal_types(self, decomposer, intent, expected_goal_types):
        result = await decomposer.decompose(intent)
        sg_ids = [sg["id"] for sg in result["sub_goals"]]
        actual_types = set()
        for sg_id in sg_ids:
            if "_research" in sg_id:
                actual_types.add("research")
            elif "_execute" in sg_id:
                actual_types.add("execute")
            elif "_report" in sg_id:
                actual_types.add("report")
            else:
                actual_types.add("single")
        assert actual_types == expected_goal_types, (
            f"Expected goal types {expected_goal_types}, got {actual_types}"
        )

    @pytest.mark.asyncio
    async def test_research_execute_dependency_chain(self, decomposer):
        """Research must complete before execute can run."""
        result = await decomposer.decompose("research and execute")
        research_sg = [sg for sg in result["sub_goals"] if "_research" in sg["id"]][0]
        execute_sg = [sg for sg in result["sub_goals"] if "_execute" in sg["id"]][0]
        # Execute depends on research
        assert research_sg["id"] in execute_sg["dependencies"]

    @pytest.mark.asyncio
    async def test_execute_report_dependency_chain(self, decomposer):
        """Execute must complete before report can run."""
        result = await decomposer.decompose("execute and report")
        execute_sg = [sg for sg in result["sub_goals"] if "_execute" in sg["id"]][0]
        report_sg = [sg for sg in result["sub_goals"] if "_report" in sg["id"]][0]
        assert execute_sg["id"] in report_sg["dependencies"]

    @pytest.mark.asyncio
    async def test_research_execute_report_full_chain(self, decomposer):
        """Full chain: research → execute → report (sequential)."""
        result = await decomposer.decompose("research then execute then report")
        research_sg = [sg for sg in result["sub_goals"] if "_research" in sg["id"]][0]
        execute_sg = [sg for sg in result["sub_goals"] if "_execute" in sg["id"]][0]
        report_sg = [sg for sg in result["sub_goals"] if "_report" in sg["id"]][0]

        # Execute depends on research
        assert research_sg["id"] in execute_sg["dependencies"]
        # Report depends on execute (which transitively depends on research)
        assert execute_sg["id"] in report_sg["dependencies"]

    @pytest.mark.asyncio
    async def test_parallel_phases_with_mixed_intent(self, decomposer):
        """Verify parallel_phases groups correctly.

        For research + execute + report, research is phase 0 (no deps),
        execute is phase 1 (depends on research),
        report is phase 2 (depends on execute).
        """
        result = await decomposer.decompose("research run document")
        phases = result["parallel_phases"]
        # Phase 0: research
        # Phase 1: execute
        # Phase 2: report
        assert len(phases) >= 2

        research_id = [sg["id"] for sg in result["sub_goals"] if "_research" in sg["id"]][0]
        assert research_id in phases[0]

# ==============================================================
# SINGLE GOAL (NO KEYWORD MATCH)
# ==============================================================

class TestSingleGoal:
    """Intents with no recognized keywords produce a single generic sub-goal."""

    @pytest.mark.parametrize("intent", [
        "what is the weather today",
        "hello world",
        "ping the server",
        "",
        "a",
    ])
    @pytest.mark.asyncio
    async def test_no_match_produces_single_goal(self, decomposer, intent):
        result = await decomposer.decompose(intent)
        assert len(result["sub_goals"]) == 1
        assert "_single" in result["sub_goals"][0]["id"]

    @pytest.mark.asyncio
    async def test_single_goal_assigned_no_agent(self, decomposer):
        """When no route matches, assigned_agent is None."""
        result = await decomposer.decompose("do a barrel roll")
        sg = result["sub_goals"][0]
        assert sg["assigned_agent"] is None

    @pytest.mark.asyncio
    async def test_single_goal_has_no_dependencies(self, decomposer):
        result = await decomposer.decompose("random intent")
        assert result["sub_goals"][0]["dependencies"] == []

    @pytest.mark.asyncio
    async def test_single_goal_estimated_complexity(self, decomposer):
        result = await decomposer.decompose("simple task")
        assert result["estimated_complexity"] == 1

# ==============================================================
# STRUCTURAL & EDGE CASES
# ==============================================================

class TestStructuralProperties:
    """Verify decomposer structural outputs: goal_id, phases, complexity."""

    @pytest.mark.asyncio
    async def test_goal_id_is_deterministic(self, decomposer):
        """Same intent produces the same goal_id."""
        r1 = await decomposer.decompose("research and execute and report")
        r2 = await decomposer.decompose("research and execute and report")
        assert r1["goal_id"] == r2["goal_id"]

    @pytest.mark.asyncio
    async def test_goal_id_differs_for_different_intents(self, decomposer):
        r1 = await decomposer.decompose("find the bug")
        r2 = await decomposer.decompose("deploy the fix")
        assert r1["goal_id"] != r2["goal_id"]

    @pytest.mark.asyncio
    async def test_original_intent_preserved(self, decomposer):
        intent = "research, exploit, and report the findings"
        result = await decomposer.decompose(intent)
        assert result["original_intent"] == intent

    @pytest.mark.asyncio
    async def test_estimated_complexity_matches_subgoal_count(self, decomposer):
        intent = "research and build and document"
        result = await decomposer.decompose(intent)
        assert result["estimated_complexity"] == len(result["sub_goals"])

    @pytest.mark.asyncio
    async def test_all_sub_goals_have_unique_ids(self, decomposer):
        result = await decomposer.decompose("research execute report")
        sg_ids = [sg["id"] for sg in result["sub_goals"]]
        assert len(sg_ids) == len(set(sg_ids)), "Sub-goal IDs must be unique"

    @pytest.mark.asyncio
    async def test_all_sub_goals_start_pending(self, decomposer):
        result = await decomposer.decompose("find and run and summarize")
        for sg in result["sub_goals"]:
            assert sg["status"] == "pending"

    @pytest.mark.asyncio
    async def test_sub_goal_has_created_at_timestamp(self, decomposer):
        result = await decomposer.decompose("research the network")
        from datetime import datetime, timezone
        created = result["sub_goals"][0]["created_at"]
        # Verify it's an ISO-8601 timestamp
        parsed = datetime.fromisoformat(created)
        assert parsed.tzinfo is not None

# ==============================================================
# AGENT ASSIGNMENT
# ==============================================================

class TestAgentAssignment:
    """Verify sub-goals are assigned to the correct agent from route()."""

    @pytest.mark.asyncio
    async def test_research_agent_assigned(self, decomposer):
        result = await decomposer.decompose("find the issue")
        sg = [s for s in result["sub_goals"] if "_research" in s["id"]][0]
        assert sg["assigned_agent"] == "researcher"

    @pytest.mark.asyncio
    async def test_research_agent_assigned(self, decomposer):
        result = await decomposer.decompose("find the issue")
        rg = [s for s in result["sub_goals"] if "_research" in s["id"]][0]
        assert rg["assigned_agent"] == "researcher"

    @pytest.mark.asyncio
    async def test_execute_agent_assigned(self, decomposer):
        result = await decomposer.decompose("build the binary")
        eg = [s for s in result["sub_goals"] if "_execute" in s["id"]][0]
        assert eg["assigned_agent"] == "executor"

    @pytest.mark.asyncio
    async def test_report_agent_assigned(self, decomposer):
        result = await decomposer.decompose("document the test")
        rg = [s for s in result["sub_goals"] if "_report" in s["id"]][0]
        assert rg["assigned_agent"] == "reporter"

    @pytest.mark.asyncio
    async def test_each_sub_goal_gets_own_agent(self, decomposer):
        """Mixed intent: each sub-goal gets its matching agent."""
        result = await decomposer.decompose("research, build, and document")
        agents = {}
        for sg in result["sub_goals"]:
            if "_research" in sg["id"]:
                agents["research"] = sg["assigned_agent"]
            elif "_execute" in sg["id"]:
                agents["execute"] = sg["assigned_agent"]
            elif "_report" in sg["id"]:
                agents["report"] = sg["assigned_agent"]
        assert agents.get("research") == "researcher"
        assert agents.get("execute") == "executor"
        assert agents.get("report") == "reporter"