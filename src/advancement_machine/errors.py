"""
Standardized error response module for MCP compliance.

Provides consistent error handling across CLI and MCP server.
All errors use a standardized format with code, message, details, timestamp, and request_id.

Usage:
    from advancement_machine.errors import ErrorResponse, ErrorCode

    error = ErrorResponse(
        code=ErrorCode.INVALID_INPUT,
        message="Event type is required",
        details={"required_fields": ["event_type"]}
    )

    # Convert to dict for JSON serialization
    error_dict = error.to_dict()
    # → {"error": {"code": "INVALID_INPUT", "message": "...", ...}}
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import uuid
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR CODES
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorCode:
    """Standard error codes for MCP compliance."""

    # Client errors (4xx equivalent)
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    INVALID_STATE = "INVALID_STATE"
    RATE_LIMITED = "RATE_LIMITED"

    # Server errors (5xx equivalent)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    OPERATION_TIMEOUT = "OPERATION_TIMEOUT"

    # Domain-specific errors
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR RESPONSE (MCP-compliant)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ErrorResponse:
    """
    Standardized error response for MCP compliance.

    All errors contain:
    - code: Machine-readable error code
    - message: Human-readable error message
    - details: Optional additional context (dict)
    - timestamp: ISO 8601 timestamp of error
    - request_id: Unique request identifier for tracking
    """

    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if not self.request_id:
            self.request_id = str(uuid.uuid4())[:12]

    def to_dict(self) -> Dict[str, Any]:
        error_data = {
            "code": self.code,
            "message": self.message,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
        }
        if self.details:
            error_data["details"] = self.details
        return {"error": error_data}

    def to_json_string(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# EXCEPTION CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class InsufficientDataError(Exception):
    """Raised when there's not enough data for an operation."""
    pass


class ScheduleNotFoundError(Exception):
    """Raised when a schedule ID is not found."""
    pass


class EventNotFoundError(Exception):
    """Raised when an event is not found."""
    pass


class InvalidStateError(Exception):
    """Raised when operation cannot be performed in current state."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR CATEGORY + DOMAIN ERRORS
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorCategory(Enum):
    """Categories of errors that can occur in the system."""
    RUNTIME = "runtime_error"
    CONFIG = "config_error"
    PLUGIN = "plugin_error"
    NETWORK = "network_error"
    VALIDATION = "validation_error"
    STATE = "state_error"


class AdvError(Exception):
    """Base error class for Advancement Machine with categorization."""

    def __init__(
        self,
        category: ErrorCategory,
        code: str,
        user_message: str,
        resolution: str = "",
        details: Optional[Dict[str, Any]] = None
    ):
        self.category = category
        self.code = code
        self.user_message = user_message
        self.resolution = resolution
        self.details = details or {}
        super().__init__(user_message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "code": self.code,
            "user_message": self.user_message,
            "resolution": self.resolution,
            "details": self.details,
        }


class ConfigError(AdvError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        resolution: str = "Check configuration file and environment variables"
    ):
        super().__init__(
            category=ErrorCategory.CONFIG,
            code="CONFIG_ERROR",
            user_message=message,
            resolution=resolution,
            details=details
        )


class PluginLoadError(AdvError):
    """Raised when a plugin fails to load."""

    def __init__(
        self,
        plugin_name: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            category=ErrorCategory.PLUGIN,
            code="PLUGIN_LOAD_ERROR",
            user_message=f"Failed to load plugin '{plugin_name}': {reason}",
            resolution=f"Check plugin '{plugin_name}' installation and configuration",
            details=details or {"plugin_name": plugin_name, "reason": reason}
        )


class NetworkError(AdvError):
    """Raised when a network operation fails."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        resolution: str = "Check network connectivity and retry"
    ):
        super().__init__(
            category=ErrorCategory.NETWORK,
            code="NETWORK_ERROR",
            user_message=message,
            resolution=resolution,
            details=details
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def create_error_response(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    exception: Optional[Exception] = None
) -> Dict[str, Any]:
    """
    Convenience function to create error response dict.

    Args:
        code: Error code from ErrorCode
        message: Human-readable message
        details: Optional context dict
        exception: Optional exception to extract information from

    Returns:
        Standardized error dict ready for JSON serialization
    """
    if details is None:
        details = {}

    if exception:
        details["exception_type"] = type(exception).__name__
        details["exception_message"] = str(exception)

    error = ErrorResponse(
        code=code,
        message=message,
        details=details if details else None
    )

    return error.to_dict()
