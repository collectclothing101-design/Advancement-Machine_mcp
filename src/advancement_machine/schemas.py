"""
Input validation schemas for all MCP operations.

Provides validation for:
  - record_event: Record temporal events
  - query_events: Query events with filters
  - forecast: Forecast future occurrences
  - schedule_at: Schedule delayed callbacks

Each schema provides:
  - Type validation
  - Required field checking
  - Value range validation
  - Helpful error messages

Usage:
    from advancement_machine.schemas import RecordEventInput
    
    try:
        input_obj = RecordEventInput.from_dict({
            "event_type": "user_login",
            "data": {"user": "alice"}
        })
        # Use input_obj...
    except ValueError as e:
        print(f"Validation error: {e}")
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


@dataclass
class RecordEventInput:
    """
    Validation schema for recording temporal events.
    
    Required:
      - event_type: str (non-empty)
    
    Optional:
      - data: Dict[str, Any] (default: {})
      - source: str (default: None)
      - ttl: float (default: None, seconds)
    """
    event_type: str
    data: Dict[str, Any] = None
    source: Optional[str] = None
    ttl: Optional[float] = None
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.event_type or not isinstance(self.event_type, str):
            raise ValidationError("event_type must be non-empty string")
        
        if self.data is None:
            self.data = {}
        elif not isinstance(self.data, dict):
            raise ValidationError("data must be dict or null")
        
        if self.ttl is not None:
            if not isinstance(self.ttl, (int, float)):
                raise ValidationError("ttl must be number (seconds)")
            if self.ttl < 0:
                raise ValidationError("ttl must be non-negative")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "RecordEventInput":
        """
        Create from input dict.
        
        Raises ValidationError on invalid input.
        """
        if not d.get("event_type"):
            raise ValidationError(
                "Missing required field: event_type (string, non-empty)"
            )
        
        return cls(
            event_type=d["event_type"],
            data=d.get("data"),
            source=d.get("source"),
            ttl=d.get("ttl")
        )


@dataclass
class QueryEventsInput:
    """
    Validation schema for querying temporal events.
    
    Optional:
      - event_type: str (filter by type)
      - since: float (filter events after timestamp)
      - until: float (filter events before timestamp)
      - source: str (filter by source)
      - limit: int (default: 100, max results)
    """
    event_type: Optional[str] = None
    since: Optional[float] = None
    until: Optional[float] = None
    source: Optional[str] = None
    limit: int = 100
    
    def __post_init__(self):
        """Validate after initialization."""
        if self.limit is not None:
            if not isinstance(self.limit, int):
                raise ValidationError("limit must be integer")
            if self.limit < 1:
                raise ValidationError("limit must be >= 1")
            if self.limit > 10000:
                raise ValidationError("limit must be <= 10000")
        
        if self.since is not None:
            if not isinstance(self.since, (int, float)):
                raise ValidationError("since must be number (timestamp)")
        
        if self.until is not None:
            if not isinstance(self.until, (int, float)):
                raise ValidationError("until must be number (timestamp)")
        
        if self.since is not None and self.until is not None:
            if self.since > self.until:
                raise ValidationError("since must be <= until")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "QueryEventsInput":
        """Create from input dict."""
        return cls(
            event_type=d.get("event_type"),
            since=d.get("since"),
            until=d.get("until"),
            source=d.get("source"),
            limit=d.get("limit", 100)
        )


@dataclass
class ForecastInput:
    """
    Validation schema for forecasting event occurrences.
    
    Required:
      - event_type: str (non-empty)
    
    Optional:
      - horizon: float (default: 3600 seconds = 1 hour)
      - min_data_points: int (default: 5, min for forecast)
    """
    event_type: str
    horizon: float = 3600
    min_data_points: int = 5
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.event_type or not isinstance(self.event_type, str):
            raise ValidationError("event_type must be non-empty string")
        
        if not isinstance(self.horizon, (int, float)):
            raise ValidationError("horizon must be number (seconds)")
        if self.horizon <= 0:
            raise ValidationError("horizon must be > 0")
        
        if not isinstance(self.min_data_points, int):
            raise ValidationError("min_data_points must be integer")
        if self.min_data_points < 1:
            raise ValidationError("min_data_points must be >= 1")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "ForecastInput":
        """Create from input dict."""
        if not d.get("event_type"):
            raise ValidationError(
                "Missing required field: event_type (string, non-empty)"
            )
        
        return cls(
            event_type=d["event_type"],
            horizon=d.get("horizon", 3600),
            min_data_points=d.get("min_data_points", 5)
        )


@dataclass
class ScheduleInput:
    """
    Validation schema for scheduling delayed operations.
    
    Required:
      - name: str (task name)
      - delay: float (seconds until execution)
    
    Optional:
      - payload: Dict[str, Any] (data to pass to callback)
    """
    name: str
    delay: float
    payload: Dict[str, Any] = None
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.name or not isinstance(self.name, str):
            raise ValidationError("name must be non-empty string")
        
        if not isinstance(self.delay, (int, float)):
            raise ValidationError("delay must be number (seconds)")
        if self.delay < 0:
            raise ValidationError("delay must be non-negative")
        
        if self.payload is None:
            self.payload = {}
        elif not isinstance(self.payload, dict):
            raise ValidationError("payload must be dict or null")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "ScheduleInput":
        """Create from input dict."""
        if not d.get("name"):
            raise ValidationError(
                "Missing required field: name (string, non-empty)"
            )
        
        delay = d.get("delay")
        if delay is None:
            raise ValidationError("Missing required field: delay (number, seconds)")
        
        return cls(
            name=d["name"],
            delay=delay,
            payload=d.get("payload")
        )


@dataclass
class CancelScheduleInput:
    """
    Validation schema for cancelling scheduled operations.
    
    Required:
      - schedule_id: str (non-empty)
    """
    schedule_id: str
    
    def __post_init__(self):
        """Validate after initialization."""
        if not self.schedule_id or not isinstance(self.schedule_id, str):
            raise ValidationError("schedule_id must be non-empty string")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "CancelScheduleInput":
        """Create from input dict."""
        if not d.get("schedule_id"):
            raise ValidationError(
                "Missing required field: schedule_id (string, non-empty)"
            )
        
        return cls(schedule_id=d["schedule_id"])


@dataclass
class SummaryInput:
    """
    Validation schema for summary statistics.
    
    Optional:
      - event_type: str (filter by type)
      - time_window: float (seconds, default: 3600)
    """
    event_type: Optional[str] = None
    time_window: float = 3600
    
    def __post_init__(self):
        """Validate after initialization."""
        if not isinstance(self.time_window, (int, float)):
            raise ValidationError("time_window must be number (seconds)")
        if self.time_window <= 0:
            raise ValidationError("time_window must be > 0")
    
    @classmethod
    def from_dict(cls, d: Dict) -> "SummaryInput":
        """Create from input dict."""
        return cls(
            event_type=d.get("event_type"),
            time_window=d.get("time_window", 3600)
        )


def validate_input(input_class, data: Dict) -> Any:
    """
    Convenience function to validate and convert input.
    
    Args:
        input_class: Input validation class (RecordEventInput, etc.)
        data: Input dict to validate
        
    Returns:
        Validated input object
        
    Raises:
        ValidationError on invalid input
    """
    return input_class.from_dict(data)
