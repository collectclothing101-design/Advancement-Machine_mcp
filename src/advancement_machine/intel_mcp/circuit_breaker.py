"""
Circuit Breaker Pattern - Phase 2

Implements resilience pattern: fail-fast after repeated errors, with automatic
recovery attempts. Prevents cascading failures in microservice architecture.

States:
- CLOSED: Normal operation, calls go through
- OPEN: After failure threshold, block calls (fail-fast)
- HALF_OPEN: Testing recovery, allow single call

Reference: Netflix Hystrix, AWS SDK patterns
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional, Dict, Any, TypeVar, Generic, Awaitable
import asyncio
import logging

logger = logging.getLogger("gitmcp.circuit_breaker")

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, block calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerMetrics:
    """Metrics collected by circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    consecutive_failures: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dict."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_state_change": self.last_state_change.isoformat(),
            "consecutive_failures": self.consecutive_failures,
            "success_rate": (
                self.success_count / (self.success_count + self.failure_count)
                if (self.success_count + self.failure_count) > 0
                else 0.0
            )
        }


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit is open."""
    pass


class CircuitBreakerTimeout(Exception):
    """Exception raised when circuit operation times out."""
    pass


class CircuitBreaker(Generic[T]):
    """
    Circuit breaker: prevents cascading failures.
    
    Fails fast after repeated errors instead of waiting for timeouts.
    Automatically attempts recovery after timeout period expires.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
        monitor_window: int = 120  # Track metrics over this window
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Identifier for this breaker (e.g., "gist:fetch_raw")
            failure_threshold: Failures to trigger OPEN state
            success_threshold: Successes to transition from HALF_OPEN -> CLOSED
            timeout_seconds: Seconds before attempting recovery
            monitor_window: Seconds over which to track metrics
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.monitor_window = monitor_window
        
        self.metrics = CircuitBreakerMetrics()
    
    async def execute(
        self,
        coro: Awaitable[T],
        timeout: int = 30
    ) -> T:
        """
        Execute coroutine through circuit breaker.
        
        Args:
            coro: Async function to execute
            timeout: Timeout in seconds for operation
        
        Returns:
            Result of coro
        
        Raises:
            CircuitBreakerOpen: If circuit is open (failing)
            CircuitBreakerTimeout: If operation exceeds timeout
            Exception: Any exception from the coro
        """
        # Check state and potentially transition
        self._check_state()
        
        if self.metrics.state == CircuitState.OPEN:
            logger.warning(f"Circuit {self.name} is OPEN - failing fast")
            raise CircuitBreakerOpen(
                f"Circuit breaker {self.name} is open after "
                f"{self.metrics.consecutive_failures} consecutive failures"
            )
        
        try:
            # Execute with timeout protection
            result = await asyncio.wait_for(coro, timeout=timeout)
            self._on_success()
            return result
        
        except asyncio.TimeoutError:
            logger.error(f"Circuit {self.name} timed out (>{timeout}s)")
            self._on_failure()
            raise CircuitBreakerTimeout(
                f"Operation on {self.name} exceeded {timeout}s timeout"
            )
        
        except Exception as e:
            logger.error(f"Circuit {self.name} failed: {str(e)}")
            self._on_failure()
            raise
    
    def _check_state(self):
        """Transition state if conditions met."""
        now = datetime.now(timezone.utc)
        
        if self.metrics.state == CircuitState.OPEN:
            # Check if enough time passed to attempt recovery
            time_since_failure = now - (
                self.metrics.last_failure_time or now
            )
            
            if time_since_failure >= timedelta(seconds=self.timeout_seconds):
                logger.info(f"Circuit {self.name} transitioning to HALF_OPEN (timeout expired)")
                self.metrics.state = CircuitState.HALF_OPEN
                self.metrics.last_state_change = now
                self.metrics.consecutive_failures = 0
    
    def _on_success(self):
        """Handle successful execution."""
        self.metrics.success_count += 1
        self.metrics.consecutive_failures = 0
        
        # Transition from HALF_OPEN to CLOSED after success_threshold successes
        if self.metrics.state == CircuitState.HALF_OPEN:
            # In HALF_OPEN, one success means recovery is working
            logger.info(f"Circuit {self.name} recovered - transitioning to CLOSED")
            self.metrics.state = CircuitState.CLOSED
            self.metrics.last_state_change = datetime.now(timezone.utc)
    
    def _on_failure(self):
        """Handle failed execution."""
        self.metrics.failure_count += 1
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure_time = datetime.now(timezone.utc)
        
        # Transition to OPEN if threshold exceeded
        if (
            self.metrics.consecutive_failures >= self.failure_threshold
            and self.metrics.state != CircuitState.OPEN
        ):
            logger.warning(
                f"Circuit {self.name} opened after "
                f"{self.metrics.consecutive_failures} failures"
            )
            self.metrics.state = CircuitState.OPEN
            self.metrics.last_state_change = datetime.now(timezone.utc)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.to_dict()
    
    def reset(self):
        """Manually reset circuit breaker."""
        logger.info(f"Circuit {self.name} manually reset")
        self.metrics = CircuitBreakerMetrics()


# Global circuit breaker pool
_CIRCUIT_BREAKERS: Dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    timeout_seconds: int = 60
) -> CircuitBreaker:
    """
    Get or create circuit breaker for a task.
    
    Args:
        name: Circuit breaker identifier
        failure_threshold: Failures to trigger open state
        timeout_seconds: Seconds before attempting recovery
    
    Returns:
        CircuitBreaker instance
    """
    if name not in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds
        )
    return _CIRCUIT_BREAKERS[name]


def reset_breaker(name: str):
    """Reset a specific circuit breaker."""
    if name in _CIRCUIT_BREAKERS:
        _CIRCUIT_BREAKERS[name].reset()


def reset_all_breakers():
    """Reset all circuit breakers."""
    for breaker in _CIRCUIT_BREAKERS.values():
        breaker.reset()


def get_breaker_status(name: str) -> Optional[Dict[str, Any]]:
    """Get status of specific breaker."""
    if name in _CIRCUIT_BREAKERS:
        return _CIRCUIT_BREAKERS[name].get_metrics()
    return None


def get_all_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all breakers."""
    return {
        name: breaker.get_metrics()
        for name, breaker in _CIRCUIT_BREAKERS.items()
    }
