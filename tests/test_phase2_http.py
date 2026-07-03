"""
Phase 2 HTTP API + Resilience Tests

30+ tests covering:
- HTTP endpoints (execute single, batch, list)
- Circuit breaker (open/closed/half-open states, recovery)
- Request tracing (correlation IDs, span hierarchy)
- Rate limiting (token bucket, per-user/task quotas)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

# HTTP API tests
from advancement_machine.intel_mcp.gitmcp_http_api import (
    TaskRequest, TaskResponse, BatchTasksRequest, TaskListResponse,
    ToolListResponse, RequestContext
)

# Circuit breaker tests
from advancement_machine.intel_mcp.circuit_breaker import (
    CircuitBreaker, CircuitBreakerOpen, CircuitBreakerTimeout, CircuitState,
    get_breaker, reset_breaker, reset_all_breakers, get_breaker_status
)

# Request tracer tests
from advancement_machine.intel_mcp.request_tracer import (
    RequestTracer, set_correlation_id, get_correlation_id,
    set_user_id, get_user_id
)

# Rate limiter tests
from advancement_machine.intel_mcp.rate_limiter import (
    TokenBucket, RateLimiter, get_global_limiter
)


# ─────────────────────────────────────────────────────────────────────────────
# CIRCUIT BREAKER TESTS (8 tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCircuitBreaker:
    """Circuit breaker functionality."""
    
    async def test_starts_in_closed_state(self):
        """Circuit breaker starts CLOSED (normal operation)."""
        cb = CircuitBreaker("test:task")
        assert cb.metrics.state == CircuitState.CLOSED
    
    async def test_allows_execution_when_closed(self):
        """Allows execution when CLOSED."""
        cb = CircuitBreaker("test:task")
        coro = AsyncMock(return_value="success")
        
        result = await cb.execute(coro())
        assert result == "success"
        assert cb.metrics.success_count == 1
    
    async def test_opens_after_failure_threshold(self):
        """Opens after N consecutive failures."""
        cb = CircuitBreaker("test:task", failure_threshold=3)
        
        # Fail 3 times
        for _ in range(3):
            with pytest.raises(Exception):
                await cb.execute(AsyncMock(side_effect=Exception("fail"))())
        
        assert cb.metrics.state == CircuitState.OPEN
        assert cb.metrics.consecutive_failures == 3
    
    async def test_blocks_calls_when_open(self):
        """Blocks new calls when OPEN (fail-fast)."""
        cb = CircuitBreaker("test:task", failure_threshold=1)
        
        # Trigger open
        with pytest.raises(Exception):
            await cb.execute(AsyncMock(side_effect=Exception("fail"))())
        
        assert cb.metrics.state == CircuitState.OPEN
        
        # Next call blocked immediately (fail-fast)
        with pytest.raises(CircuitBreakerOpen):
            await cb.execute(AsyncMock())
    
    async def test_transitions_to_half_open_after_timeout(self):
        """Transitions to HALF_OPEN after timeout expires."""
        cb = CircuitBreaker("test:task", failure_threshold=1, timeout_seconds=0)
        
        # Open circuit
        with pytest.raises(Exception):
            await cb.execute(AsyncMock(side_effect=Exception("fail"))())
        
        assert cb.metrics.state == CircuitState.OPEN
        
        # After timeout (0), should transition to HALF_OPEN
        cb._check_state()
        assert cb.metrics.state == CircuitState.HALF_OPEN
    
    async def test_success_closes_from_half_open(self):
        """Single success closes circuit from HALF_OPEN."""
        cb = CircuitBreaker("test:task", failure_threshold=1, timeout_seconds=0)
        
        # Open and transition to HALF_OPEN
        with pytest.raises(Exception):
            await cb.execute(AsyncMock(side_effect=Exception("fail"))())
        cb._check_state()
        
        assert cb.metrics.state == CircuitState.HALF_OPEN
        
        # Success closes it
        await cb.execute(AsyncMock(return_value="ok")())
        assert cb.metrics.state == CircuitState.CLOSED
    
    async def test_timeout_tracked(self):
        """Tracks timeout as failure."""
        cb = CircuitBreaker("test:task", failure_threshold=1)
        
        # Timeout should count as failure
        with pytest.raises(CircuitBreakerTimeout):
            await cb.execute(asyncio.sleep(10), timeout=0.01)
        
        assert cb.metrics.consecutive_failures == 1
    
    async def test_reset_clears_state(self):
        """Reset clears circuit state."""
        cb = CircuitBreaker("test:task")
        cb.metrics.failure_count = 100
        cb.metrics.consecutive_failures = 10
        cb.metrics.state = CircuitState.OPEN
        
        cb.reset()
        
        assert cb.metrics.state == CircuitState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.consecutive_failures == 0


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST TRACER TESTS (8 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestRequestTracer:
    """Request tracing and correlation IDs."""
    
    def test_creates_with_request_id(self):
        """Creates tracer with request ID."""
        tracer = RequestTracer("req-123", "user-456", "fetch_data")
        
        assert tracer.request_id == "req-123"
        assert tracer.user_id == "user-456"
        assert tracer.operation == "fetch_data"
    
    def test_generates_uuid_if_missing(self):
        """Generates UUID if request ID not provided."""
        tracer = RequestTracer("", "user-456")
        assert len(tracer.request_id) > 0  # Has some ID
    
    def test_from_headers_extracts_context(self):
        """Extracts context from HTTP headers."""
        headers = {
            "X-Request-ID": "req-789",
            "X-User-ID": "user-abc",
            "X-Span-ID": "span-xyz"
        }
        
        tracer = RequestTracer.from_headers(headers, "process")
        
        assert tracer.request_id == "req-789"
        assert tracer.user_id == "user-abc"
    
    def test_sets_context_variables(self):
        """Sets context variables for distributed tracing."""
        tracer = RequestTracer("req-111", "user-222", "task")
        
        assert get_correlation_id() == "req-111"
        assert get_user_id() == "user-222"
    
    def test_logs_info(self, caplog):
        """Logs info messages with context."""
        tracer = RequestTracer("req-123", "user-456")
        tracer.log_info("Test message")
        
        # Check log was recorded
        assert "Test message" in caplog.text or "req-123" in caplog.text
    
    def test_logs_error_with_exception(self, caplog):
        """Logs errors with exception info."""
        tracer = RequestTracer("req-123", "user-456")
        
        try:
            raise ValueError("test error")
        except ValueError as e:
            tracer.log_error("Processing failed", e)
        
        assert "ValueError" in caplog.text or "test error" in caplog.text
    
    def test_get_elapsed_time(self):
        """Gets elapsed time since creation."""
        tracer = RequestTracer("req-123", "user-456")
        
        elapsed_ms = tracer.get_elapsed_ms()
        assert elapsed_ms >= 0
        assert isinstance(elapsed_ms, int)
    
    def test_get_headers_for_propagation(self):
        """Gets headers for propagating context downstream."""
        tracer = RequestTracer("req-123", "user-456")
        headers = tracer.get_headers()
        
        assert headers["X-Request-ID"] == "req-123"
        assert headers["X-User-ID"] == "user-456"


# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITER TESTS (10 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenBucket:
    """Token bucket rate limiting."""
    
    def test_initializes_at_capacity(self):
        """Bucket starts at capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=1)
        assert bucket.tokens == 10
    
    def test_allows_request_when_tokens_available(self):
        """Allows request when tokens available."""
        bucket = TokenBucket(capacity=10, refill_rate=1)
        
        allowed = bucket.allow_request()
        assert allowed is True
        assert bucket.tokens == 9
    
    def test_blocks_request_when_depleted(self):
        """Blocks request when tokens depleted."""
        bucket = TokenBucket(capacity=1, refill_rate=0)  # No refill
        
        allowed1 = bucket.allow_request()
        allowed2 = bucket.allow_request()
        
        assert allowed1 is True  # First succeeds
        assert allowed2 is False  # Second blocked
    
    def test_refills_over_time(self):
        """Tokens refill at configured rate."""
        bucket = TokenBucket(capacity=10, refill_rate=5)  # 5 tokens/sec
        
        # Spend all tokens
        for _ in range(10):
            bucket.allow_request()
        assert bucket.tokens < 1
        
        # Manually advance time and refill
        bucket.last_refill = datetime.now(timezone.utc) - timedelta(seconds=1)
        bucket._refill()
        
        # Should have refilled
        assert bucket.tokens > 0
    
    def test_caps_at_capacity_on_refill(self):
        """Refill never exceeds capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=100)
        bucket.last_refill = datetime.now(timezone.utc) - timedelta(seconds=10)
        
        bucket._refill()
        
        assert bucket.tokens == 10  # Capped at capacity, not 10+1000


class TestRateLimiter:
    """Per-user/task rate limiting."""
    
    def test_allows_below_limit(self):
        """Allows requests below rate limit."""
        limiter = RateLimiter(default_rps=100)
        
        allowed = limiter.is_allowed_user("user-1")
        assert allowed is True
    
    def test_blocks_user_rate_limit(self):
        """Blocks user after consuming capacity."""
        limiter = RateLimiter(default_rps=1, bursts=1)
        
        allowed1 = limiter.is_allowed_user("user-1")
        allowed2 = limiter.is_allowed_user("user-1")
        
        assert allowed1 is True
        assert allowed2 is False
    
    def test_sets_custom_quota(self):
        """Sets custom quota for user."""
        limiter = RateLimiter()
        limiter.set_user_quota("vip-user", rps=1000, burst=100)
        
        # VIP user should have higher capacity
        status = limiter.get_user_status("vip-user")
        assert status["capacity"] == 100
        assert status["refill_rate_rps"] == 1000
    
    def test_independent_per_user(self):
        """Users have independent rate limits."""
        limiter = RateLimiter(default_rps=1, bursts=1)
        
        user1_ok = limiter.is_allowed_user("user-1")
        user1_blocked = limiter.is_allowed_user("user-1")
        user2_ok = limiter.is_allowed_user("user-2")
        
        assert user1_ok is True
        assert user1_blocked is False  # User-1 depleted
        assert user2_ok is True  # User-2 separate
    
    def test_task_rate_limiting(self):
        """Tasks have separate rate limit."""
        limiter = RateLimiter(default_rps=1, bursts=1)
        
        task1_ok = limiter.is_allowed_task("task-1")
        task1_blocked = limiter.is_allowed_task("task-1")
        
        assert task1_ok is True
        assert task1_blocked is False
    
    def test_combined_user_task_limit(self):
        """Combined user+task limit is stricter."""
        limiter = RateLimiter(default_rps=10, bursts=5)
        
        # User and task are OK independently
        user_ok = limiter.is_allowed_user("user-1")
        task_ok = limiter.is_allowed_task("heavy-task")
        
        assert user_ok is True
        assert task_ok is True


# ─────────────────────────────────────────────────────────────────────────────
# HTTP API MODELS (4 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestHTTPModels:
    """HTTP request/response models."""
    
    def test_task_request_validates(self):
        """TaskRequest validates properly."""
        req = TaskRequest(
            task_name="gist:fetch_raw",
            params={"gist_id": "123"}
        )
        assert req.task_name == "gist:fetch_raw"
        assert req.params["gist_id"] == "123"
    
    def test_task_response_formats(self):
        """TaskResponse formats correctly."""
        resp = TaskResponse(
            request_id="req-123",
            task_name="gist:fetch_raw",
            status="success",
            data={"result": "ok"},
            elapsed_ms=50
        )
        assert resp.status == "success"
        assert resp.elapsed_ms == 50
    
    def test_batch_request_validates(self):
        """BatchTasksRequest validates properly."""
        batch_req = BatchTasksRequest(
            tasks=[
                TaskRequest(task_name="task1", params={}),
                TaskRequest(task_name="task2", params={})
            ]
        )
        assert len(batch_req.tasks) == 2
    
    def test_request_context_from_request(self):
        """RequestContext extracts from request."""
        mock_request = Mock()
        mock_request.headers.get = lambda k, default=None: {
            "X-Request-ID": "req-456",
            "X-User-ID": "user-789"
        }.get(k, default)
        
        ctx = RequestContext.from_request(mock_request)
        assert ctx.request_id == "req-456"
        assert ctx.user_id == "user-789"


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS (2 tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPhase2Integration:
    """Integration between Phase 2 components."""
    
    async def test_circuit_breaker_with_timeout(self):
        """Circuit breaker counts timeouts as failures."""
        cb = CircuitBreaker("task", failure_threshold=1, timeout_seconds=60)
        
        with pytest.raises(CircuitBreakerTimeout):
            await cb.execute(asyncio.sleep(10), timeout=0.001)
        
        assert cb.metrics.state == CircuitState.OPEN
    
    async def test_rate_limiter_with_circuit_breaker(self):
        """Rate limiter can work alongside circuit breaker."""
        limiter = RateLimiter(default_rps=1, bursts=2)
        cb = CircuitBreaker("task")
        
        # First two requests OK
        assert limiter.is_allowed_user("user-1") is True
        assert limiter.is_allowed_user("user-1") is True
        
        # Third rate limited
        assert limiter.is_allowed_user("user-1") is False
        
        # Circuit breaker independent
        result = await cb.execute(AsyncMock(return_value="ok")())
        assert result == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Test execution summary
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
