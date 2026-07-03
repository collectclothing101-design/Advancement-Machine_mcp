"""
Request Tracer - Phase 2

Provides structured logging with correlation IDs for distributed tracing.
Enables debugging across service boundaries using correlation_id.

Pattern: Context variables + structured logging
"""

from contextvars import ContextVar
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from enum import Enum


class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Context variable: correlation ID for request tracing
_CORRELATION_ID: ContextVar[str] = ContextVar(
    "correlation_id",
    default=""
)

# Context variable: user ID for tracking
_USER_ID: ContextVar[str] = ContextVar(
    "user_id",
    default="anonymous"
)

# Context variable: span ID for nested operations
_SPAN_ID: ContextVar[str] = ContextVar(
    "span_id",
    default=""
)


class RequestTracer:
    """
    Structured logging with distributed tracing support.
    
    Tracks requests across service boundaries using correlation IDs.
    Supports hierarchical spans for nested operations.
    """
    
    def __init__(
        self,
        request_id: str,
        user_id: str = "anonymous",
        operation: str = "untitled"
    ):
        """
        Initialize request tracer.
        
        Args:
            request_id: Unique request identifier (correlation ID)
            user_id: User who initiated request
            operation: High-level operation name
        """
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id or "anonymous"
        self.operation = operation
        self.created_at = datetime.now(timezone.utc)
        self.span_stack: list[str] = []
        
        # Set context variables
        _CORRELATION_ID.set(self.request_id)
        _USER_ID.set(self.user_id)
        
        # Get logger
        self.logger = logging.getLogger("gitmcp.tracer")
        
        # Log creation
        self._log(
            LogLevel.INFO,
            f"Request started: {self.operation}",
            {
                "request_id": self.request_id,
                "user_id": self.user_id,
                "operation": self.operation
            }
        )
    
    @staticmethod
    def from_headers(
        headers: Dict[str, str],
        operation: str = "untitled"
    ) -> "RequestTracer":
        """
        Create tracer from HTTP headers.
        
        Looks for:
        - X-Request-ID: correlation ID (creates new if missing)
        - X-User-ID: user identifier
        - X-Span-ID: parent span (for nested calls)
        
        Args:
            headers: HTTP headers dict
            operation: Operation name
        
        Returns:
            RequestTracer instance
        """
        request_id = headers.get("X-Request-ID") or str(uuid.uuid4())
        user_id = headers.get("X-User-ID", "anonymous")
        
        tracer = RequestTracer(request_id, user_id, operation)
        
        # Set span if provided
        span_id = headers.get("X-Span-ID")
        if span_id:
            _SPAN_ID.set(span_id)
        
        return tracer
    
    @staticmethod
    def from_context() -> "RequestTracer":
        """Create tracer from current context variables."""
        request_id = _CORRELATION_ID.get("") or str(uuid.uuid4())
        user_id = _USER_ID.get("anonymous")
        return RequestTracer(request_id, user_id, "context_operation")
    
    def create_child_span(self, operation: str) -> "RequestTracer":
        """
        Create child operation tracer (nested context).
        
        Args:
            operation: Child operation name
        
        Returns:
            New RequestTracer with same request_id
        """
        child = RequestTracer(self.request_id, self.user_id, operation)
        return child
    
    def log_info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log info message."""
        self._log(LogLevel.INFO, message, extra)
    
    def log_warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, extra)
    
    def log_error(
        self,
        message: str,
        error: Optional[Exception] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        """Log error message."""
        if extra is None:
            extra = {}
        if error:
            extra["error_type"] = type(error).__name__
            extra["error_message"] = str(error)
        self._log(LogLevel.ERROR, message, extra, exc_info=error)
    
    def log_debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, extra)
    
    def _log(
        self,
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: Optional[Exception] = None
    ):
        """Internal log with structured context."""
        # Build context dict
        context = {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "operation": self.operation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if extra:
            context.update(extra)
        
        # Prepare message with context
        formatted_msg = f"[{self.request_id}] {message}"
        
        # Log at appropriate level
        log_method = getattr(self.logger, level.value.lower())
        log_method(
            formatted_msg,
            extra=context,
            exc_info=exc_info
        )
    
    def record_metric(self, metric_name: str, value: float, unit: str = ""):
        """Record a metric value."""
        self.log_debug(
            f"Metric recorded: {metric_name}",
            {
                "metric_name": metric_name,
                "metric_value": value,
                "metric_unit": unit
            }
        )
    
    def get_elapsed_ms(self) -> int:
        """Get elapsed time since tracer creation."""
        elapsed = datetime.now(timezone.utc) - self.created_at
        return int(elapsed.total_seconds() * 1000)
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers for propagating context to downstream services."""
        headers = {
            "X-Request-ID": self.request_id,
            "X-User-ID": self.user_id,
        }
        
        span_id = _SPAN_ID.get("")
        if span_id:
            headers["X-Span-ID"] = span_id
        
        return headers
    
    def close(self):
        """Log request completion."""
        elapsed_ms = self.get_elapsed_ms()
        self.log_info(
            f"Request completed: {self.operation}",
            {
                "elapsed_ms": elapsed_ms,
                "elapsed_seconds": elapsed_ms / 1000
            }
        )


# Global request tracer pool (per-request)
_active_tracers: Dict[str, RequestTracer] = {}


def register_tracer(request_id: str, tracer: RequestTracer):
    """Register active tracer for a request."""
    _active_tracers[request_id] = tracer


def unregister_tracer(request_id: str):
    """Unregister tracer when request is done."""
    if request_id in _active_tracers:
        del _active_tracers[request_id]


def get_active_tracer(request_id: str) -> Optional[RequestTracer]:
    """Get active tracer for request."""
    return _active_tracers.get(request_id)


def set_correlation_id(request_id: str):
    """Set correlation ID in context."""
    _CORRELATION_ID.set(request_id)


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return _CORRELATION_ID.get("")


def set_user_id(user_id: str):
    """Set user ID in context."""
    _USER_ID.set(user_id)


def get_user_id() -> str:
    """Get current user ID."""
    return _USER_ID.get("anonymous")


def set_span_id(span_id: str):
    """Set span ID for hierarchical tracing."""
    _SPAN_ID.set(span_id)


def get_span_id() -> str:
    """Get current span ID."""
    return _SPAN_ID.get("")
