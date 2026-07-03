"""
Advancement Machine — Universal MCP/Plugin/Skill Engine

A temporal intelligence system for orchestrating complex workflows with
event recording, forecasting, scheduling, and dependency resolution.

Core Components:
- TemporalEngine: Stateless event/schedule/forecast engine
- TemporalMCPServer: MCP protocol server for AI agent integration
- CLI interface: advancement temporal [record|query|forecast|schedule|...]
- Error handling: Standardized error responses for MCP compliance

Quick Start:
    from advancement_machine import TemporalEngine
    
    engine = TemporalEngine()
    event_id = engine.record_event("user_login", {"user": "alice"})
    events = engine.query_events("user_login")
    forecast = engine.forecast("user_login", horizon=3600)
"""

__version__ = "0.4.0"
__app_name__ = "Advancement Machine"
__author__ = "EuroThrottle"

# Core engine exports
from .temporal_engine import TemporalEngine, TemporalEvent, ForecastResult

# MCP server exports
from .mcp_server import TemporalMCPServer, run_mcp_server

# Error handling exports
from .errors import (
    ErrorResponse,
    ErrorCode,
    ValidationError,
    InsufficientDataError,
    ScheduleNotFoundError,
    EventNotFoundError,
    InvalidStateError,
    create_error_response,
)

__all__ = [
    # Version info
    "__version__",
    "__app_name__",
    "__author__",
    
    # Core engine
    "TemporalEngine",
    "TemporalEvent",
    "ForecastResult",
    
    # MCP server
    "TemporalMCPServer",
    "run_mcp_server",
    
    # Error handling
    "ErrorResponse",
    "ErrorCode",
    "ValidationError",
    "InsufficientDataError",
    "ScheduleNotFoundError",
    "EventNotFoundError",
    "InvalidStateError",
    "create_error_response",
]
