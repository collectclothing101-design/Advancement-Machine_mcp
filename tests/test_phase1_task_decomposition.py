"""
Tests for Phase 1: Task Decomposition & Framework.

Tests atomic tasks in isolation:
  1. Task registration and retrieval
  2. TaskContext, TaskResult data structures
  3. Individual gist task handlers
  4. Error handling and metrics
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from advancement_machine.intel_mcp.task_framework import (
    TaskStatus,
    TaskErrorCode,
    TaskError,
    TaskValidationError,
    TaskAuthError,
    TaskMetrics,
    TaskContext,
    TaskResult,
    task_handler,
    get_task_handler,
    get_all_tasks,
    _TASK_REGISTRY,
    _TASK_SCHEMAS,
)
from advancement_machine.intel_mcp.gist_task_handlers import (
    fetch_gist_raw,
    list_user_gists_raw,
    parse_gist_content,
    extract_patterns_from_gist,
    dedupe_gist,
    score_gist,
    filter_gist_by_score,
    aggregate_gist_list,
)
from advancement_machine.intel_mcp.gist_client import GitHubGist, GistFile


# ═════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════

@pytest.fixture
def task_context():
    """Create a TaskContext for testing."""
    return TaskContext(task_name="test_task")


@pytest.fixture
def mock_gist_client():
    """Create a mock GistClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_gist_data():
    """Create mock GitHubGist data."""
    gist = MagicMock(spec=GitHubGist)
    gist.id = "test_gist_123"
    gist.url = "https://api.github.com/gists/test_gist_123"
    gist.html_url = "https://gist.github.com/testuser/test_gist_123"
    gist.owner = {"login": "testuser"}
    gist.description = "Test gist"
    gist.public = True
    gist.comments = 0
    gist.created_at = "2024-01-01T00:00:00Z"
    gist.updated_at = "2024-06-27T00:00:00Z"
    
    # Mock files
    file1 = MagicMock(spec=GistFile)
    file1.filename = "test.py"
    file1.type = "text/plain"
    file1.language = "Python"
    file1.raw_url = "https://gist.githubusercontent.com/testuser/test_gist_123/raw/test.py"
    file1.size = 100
    file1.content = "print('hello')\n"
    
    gist.files = {"test.py": file1}
    gist.get_content_hash = lambda: "abcdef1234567890"
    
    return gist


@pytest.fixture
def mock_pattern_memory():
    """Create a mock PatternMemory."""
    memory = MagicMock()
    memory.check_dedup = MagicMock(return_value=False)
    return memory


# ═════════════════════════════════════════════════════════════════════════
# Tests: Task Framework
# ═════════════════════════════════════════════════════════════════════════

class TestTaskMetrics:
    """Test TaskMetrics tracking."""

    def test_inc_counter(self):
        """Test counter increment."""
        metrics = TaskMetrics()
        metrics.inc("test_counter", 5)
        assert metrics.counters["test_counter"] == 5
        metrics.inc("test_counter", 3)
        assert metrics.counters["test_counter"] == 8

    def test_record_timing(self):
        """Test timing recording."""
        metrics = TaskMetrics()
        metrics.record_timing("task.duration", 100.5)
        metrics.record_timing("task.duration", 200.3)
        
        assert len(metrics.timings["task.duration"]) == 2
        assert metrics.timings["task.duration"][0] == 100.5

    def test_set_gauge(self):
        """Test gauge setting."""
        metrics = TaskMetrics()
        metrics.set_gauge("memory_usage", 512.0)
        assert metrics.gauges["memory_usage"] == 512.0

    def test_get_summary(self):
        """Test metrics summary."""
        metrics = TaskMetrics()
        metrics.inc("counter1", 10)
        metrics.inc("counter2", 5)
        metrics.record_timing("timing1", 100.0)
        metrics.record_timing("timing1", 200.0)
        metrics.set_gauge("gauge1", 50.0)
        
        summary = metrics.get_summary()
        assert summary["counters"]["counter1"] == 10
        assert summary["counters"]["counter2"] == 5
        assert summary["timings"]["timing1"]["count"] == 2
        assert summary["timings"]["timing1"]["avg"] == 150.0
        assert summary["gauges"]["gauge1"] == 50.0


class TestTaskContext:
    """Test TaskContext."""

    def test_create_context(self):
        """Test creating TaskContext."""
        context = TaskContext(task_name="test_task")
        assert context.task_name == "test_task"
        assert isinstance(context.metrics, TaskMetrics)
        assert context.state == {}
        assert context.config == {}

    def test_get_elapsed_ms(self):
        """Test elapsed time calculation."""
        context = TaskContext(task_name="test_task")
        elapsed = context.get_elapsed_ms()
        assert elapsed >= 0  # Should be small positive value


class TestTaskResult:
    """Test TaskResult."""

    def test_success_result(self):
        """Test creating success result."""
        result = TaskResult.success(data={"gist_id": "123"})
        assert result.status == TaskStatus.COMPLETE
        assert result.data == {"gist_id": "123"}
        assert result.error_info is None
        assert result.is_success() is True
        assert result.is_error() is False

    def test_error_result(self):
        """Test creating error result."""
        error = TaskError("Test error")
        result = TaskResult.error(error)
        assert result.status == TaskStatus.FAILED
        assert result.is_error() is True
        assert result.error_info is not None
        assert "Test error" in result.error_info["message"]

    def test_retry_result(self):
        """Test creating retry result."""
        error = Exception("Temporary failure")
        result = TaskResult.retry(error, attempt=1)
        assert result.status == TaskStatus.RETRY
        assert result.is_retry() is True


class TestTaskHandler:
    """Test task handler registration."""

    def test_register_task(self):
        """Test registering a task handler."""
        @task_handler(name="test:custom_task")
        async def custom_task(context, value: str):
            return TaskResult.success({"result": value})
        
        handler = get_task_handler("test:custom_task")
        assert handler is not None

    def test_get_all_tasks(self):
        """Test getting all registered tasks."""
        tasks = get_all_tasks()
        # Should have at least the built-in gist tasks
        assert "gist:fetch_raw" in tasks or len(tasks) > 0


# ═════════════════════════════════════════════════════════════════════════
# Tests: Gist Task Handlers
# ═════════════════════════════════════════════════════════════════════════

class TestGistTaskHandlers:
    """Test individual gist task handlers."""

    @pytest.mark.asyncio
    async def test_fetch_gist_raw_success(self, task_context, mock_gist_client, mock_gist_data):
        """Test successful gist fetch."""
        task_context.state["gist_client"] = mock_gist_client
        mock_gist_client.get_gist.return_value = mock_gist_data
        
        result = await fetch_gist_raw(task_context, "test_gist_123")
        
        assert result.is_success()
        assert result.data.id == "test_gist_123"
        assert result.metadata["file_count"] == 1
        mock_gist_client.get_gist.assert_called_once_with("test_gist_123")

    @pytest.mark.asyncio
    async def test_fetch_gist_validation_error(self, task_context):
        """Test fetch with invalid gist_id."""
        with pytest.raises(TaskValidationError):
            await fetch_gist_raw(task_context, None)

    @pytest.mark.asyncio
    async def test_parse_gist_content(self, task_context, mock_gist_data):
        """Test parsing gist content."""
        result = await parse_gist_content(task_context, mock_gist_data)
        
        assert result.is_success()
        parsed = result.data
        assert parsed["id"] == "test_gist_123"
        assert parsed["owner"] == "testuser"
        assert parsed["file_count"] == 1
        assert len(parsed["files"]) == 1
        assert parsed["files"][0]["language"] == "Python"

    @pytest.mark.asyncio
    async def test_parse_gist_validation_error(self, task_context):
        """Test parse with invalid input."""
        with pytest.raises(TaskValidationError):
            await parse_gist_content(task_context, {"invalid": "data"})

    @pytest.mark.asyncio
    async def test_dedupe_gist_no_memory(self, task_context):
        """Test dedup without pattern memory."""
        parsed_gist = {"id": "123", "content_hash": "abc123"}
        
        result = await dedupe_gist(task_context, parsed_gist)
        
        assert result.is_success()
        assert result.data["is_duplicate"] is False
        assert result.data["duplicate_score"] == 0.0

    @pytest.mark.asyncio
    async def test_dedupe_gist_with_memory(self, task_context, mock_pattern_memory):
        """Test dedup with pattern memory."""
        task_context.state["pattern_memory"] = mock_pattern_memory
        parsed_gist = {"id": "123", "content_hash": "abc123"}
        
        mock_pattern_memory.check_dedup.return_value = False
        result = await dedupe_gist(task_context, parsed_gist)
        
        assert result.is_success()
        assert result.data["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_score_gist(self, task_context):
        """Test gist scoring."""
        parsed_gist = {
            "id": "123",
            "public": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "patterns": [],
            "is_duplicate": False,
        }
        
        result = await score_gist(task_context, parsed_gist)
        
        assert result.is_success()
        score = result.data["relevance_score"]
        assert 0.0 <= score <= 1.0
        assert "recency_score" in result.metadata

    @pytest.mark.asyncio
    async def test_filter_gist_passes(self, task_context):
        """Test gist filter passes threshold."""
        gist = {"id": "123", "relevance_score": 0.8}
        
        result = await filter_gist_by_score(task_context, gist, min_score=0.5)
        
        assert result.is_success()
        assert result.data["id"] == "123"

    @pytest.mark.asyncio
    async def test_filter_gist_fails(self, task_context):
        """Test gist filter fails threshold."""
        gist = {"id": "123", "relevance_score": 0.2}
        
        result = await filter_gist_by_score(task_context, gist, min_score=0.5)
        
        assert result.status == TaskStatus.SKIPPED
        assert result.data is None

    @pytest.mark.asyncio
    async def test_aggregate_gist_list(self, task_context):
        """Test aggregating gist list."""
        gists = [
            {"id": "1", "relevance_score": 0.5},
            {"id": "2", "relevance_score": 0.9},
            {"id": "3", "relevance_score": 0.7},
        ]
        
        result = await aggregate_gist_list(task_context, gists, sort_by="relevance_score")
        
        assert result.is_success()
        sorted_gists = result.data
        assert len(sorted_gists) == 3
        # Default is descending
        assert sorted_gists[0]["relevance_score"] == 0.9
        assert sorted_gists[-1]["relevance_score"] == 0.5


# ═════════════════════════════════════════════════════════════════════════
# Tests: Error Handling
# ═════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Test error handling in tasks."""

    def test_task_error_to_dict(self):
        """Test TaskError serialization."""
        error = TaskError(
            "Test error",
            code=TaskErrorCode.VALIDATION_ERROR,
            details={"field": "gist_id"}
        )
        error_dict = error.to_dict()
        
        assert error_dict["error"] == "TaskError"
        assert error_dict["message"] == "Test error"
        assert error_dict["code"] == "validation_error"
        assert error_dict["details"]["field"] == "gist_id"

    def test_task_validation_error(self):
        """Test TaskValidationError."""
        error = TaskValidationError("Invalid input", {"value": None})
        assert error.code == TaskErrorCode.VALIDATION_ERROR

    def test_task_auth_error(self):
        """Test TaskAuthError."""
        error = TaskAuthError("Not authenticated")
        assert error.code == TaskErrorCode.AUTH_ERROR


class TestTaskMetricsInContextexecution:
    """Test metrics recording during task execution."""

    @pytest.mark.asyncio
    async def test_metrics_recorded(self, task_context):
        """Test that metrics are recorded during task execution."""
        task_context.metrics.inc("test.counter")
        task_context.metrics.record_timing("test.timing", 50.0)
        
        summary = task_context.metrics.get_summary()
        assert summary["counters"]["test.counter"] == 1
        assert summary["timings"]["test.timing"]["count"] == 1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
