import pytest
from advancement_machine.agent_orchestrator import AgentOrchestrator
@pytest.mark.asyncio
async def test_undo_forget_missing_audit_log(orchestrator: AgentOrchestrator):
    """Verify undo_forget returns False cleanly when audit_log is empty.

    This tests the case where no forget operation has ever been recorded
    for the given agent/key pair.
    """
    agent = "never_forgotten"
    key = "never_deleted"

    # Store a memory but never delete it
    await orchestrator.store_memory(agent, key, "persistent_value")

    # Attempt undo_forget — audit_log is empty for this key
    restored = await orchestrator.undo_forget(agent, key)

    # Must return False without raising an exception
    assert restored is False, (
        f"undo_forget should return False when no audit entry exists, "
        f"got {restored}"
    )

    # The memory should still be present (undo_forget should not delete it)
    val = orchestrator.memory.get(agent, key)
    assert val == "persistent_value", (
        f"Memory should remain intact after failed undo_forget, "
        f"got '{val}'"
    )

@pytest.mark.asyncio
async def test_undo_forget_after_missing_audit_log_same_key_different_agent(orchestrator: AgentOrchestrator):
    """Verify undo_forget returns False when audit_log has entries for
    a different agent with the same key.

    This ensures the agent_name filter is applied correctly.
    """
    agent_a = "agent_a"
    agent_b = "agent_b"
    shared_key = "shared_key"

    # Store and forget for agent_a
    await orchestrator.store_memory(agent_a, shared_key, "value_a")
    await orchestrator.forget_memory(agent_a, shared_key)

    # agent_b has never used this key
    restored = await orchestrator.undo_forget(agent_b, shared_key)

    assert restored is False, (
        f"undo_forget should return False for agent_b (no audit entry), "
        f"got {restored}"
    )

@pytest.mark.asyncio
async def test_undo_forget_empty_string_agent(orchestrator: AgentOrchestrator):
    """Verify undo_forget handles empty agent_name gracefully."""
    restored = await orchestrator.undo_forget("", "some_key")
    assert restored is False, "undo_forget with empty agent_name must return False"