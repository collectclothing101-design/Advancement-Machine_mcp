"""
Test that the temporal scheduler fires tasks correctly.

Focus: logical correctness (firing, cancellation, order)
not wallclock timing (too system-load dependent).
"""
import asyncio
import time
import pytest
import inspect
from advancement_machine.temporal_engine import TemporalEngine

@pytest.mark.asyncio
async def test_scheduled_task_fires_and_callback_invoked():
    """Test that a scheduled task fires and invokes the callback."""
    engine = TemporalEngine()

    # Collect firing evidence
    fired_data = []
    def capture(data):
        fired_data.append(data)

    engine.set_schedule_callback(capture)

    # Schedule a task in 100ms
    sid = engine.schedule_at("test_fire", 0.1, lambda d: None, {"marker": "test_payload"})

    # Wait for the task to be due
    await asyncio.sleep(0.2)

    # Execute due schedules
    executed = await engine.execute_scheduled()

    # Assert the schedule fired
    assert sid in executed, f"Schedule {sid} was not executed. Executed: {executed}"

    # Assert the callback received data
    assert len(fired_data) == 1, f"Expected 1 callback invocation, got {len(fired_data)}"
    assert fired_data[0]["marker"] == "test_payload"

@pytest.mark.asyncio
async def test_scheduled_task_can_be_cancelled():
    """Test that cancelled tasks do not execute."""
    engine = TemporalEngine()

    sid = engine.schedule_at("test_cancel", 0.5, lambda d: None, {})

    # Cancel before it fires
    cancelled = engine.cancel_schedule(sid)
    assert cancelled is True

    # Wait past the original schedule time
    await asyncio.sleep(0.6)

    # Execute — nothing should fire
    executed = await engine.execute_scheduled()
    assert sid not in executed, "Cancelled schedule should not execute"

@pytest.mark.asyncio
async def test_multiple_schedules_fire_in_order():
    """Test that multiple schedules fire in chronological order."""
    engine = TemporalEngine()
    order = []

    def capture(data):
        order.append(data["idx"])

    engine.set_schedule_callback(capture)

    # Schedule three tasks at different delays
    engine.schedule_at("first", 0.05, lambda d: None, {"idx": 1})
    engine.schedule_at("second", 0.1, lambda d: None, {"idx": 2})
    engine.schedule_at("third", 0.15, lambda d: None, {"idx": 3})

    # Wait for all to be due
    await asyncio.sleep(0.3)

    # Execute all due
    await engine.execute_scheduled()

    # Assert order preserved
    assert order == [1, 2, 3], f"Expected [1,2,3], got {order}"

@pytest.mark.asyncio
async def test_schedule_callback_integration():
    """Test that external callback is properly integrated with schedule execution."""
    engine = TemporalEngine()
    
    # Track callback invocations
    invocations = []
    
    def track_invocation(data):
        invocations.append({
            "timestamp": time.time(),
            "data": data
        })
    
    engine.set_schedule_callback(track_invocation)
    
    # Schedule multiple tasks
    sid1 = engine.schedule_at("task1", 0.05, lambda d: None, {"task": "first"})
    sid2 = engine.schedule_at("task2", 0.1, lambda d: None, {"task": "second"})
    
    # Wait for both to be due
    await asyncio.sleep(0.2)
    
    # Execute
    executed = await engine.execute_scheduled()
    
    # Verify
    assert len(invocations) == 2, f"Expected 2 invocations, got {len(invocations)}"
    assert invocations[0]["data"]["task"] == "first"
    assert invocations[1]["data"]["task"] == "second"
    assert sid1 in executed
    assert sid2 in executed

@pytest.mark.asyncio
async def test_schedule_returned_id_can_cancel():
    """Test that the returned schedule_id works for cancellation."""
    engine = TemporalEngine()
    
    # Schedule a task
    sid = engine.schedule_at("cancellable", 1.0, lambda d: None, {})
    
    # Verify it's in the schedules dict
    assert sid in engine.schedules
    
    # Cancel using the returned ID
    result = engine.cancel_schedule(sid)
    assert result is True
    
    # Verify it's removed
    assert sid not in engine.schedules

@pytest.mark.asyncio
async def test_non_existent_schedule_cancel_returns_false():
    """Test that cancelling a non-existent schedule returns False."""
    engine = TemporalEngine()
    
    # Try to cancel something that doesn't exist
    result = engine.cancel_schedule("nonexistent")
    assert result is False
