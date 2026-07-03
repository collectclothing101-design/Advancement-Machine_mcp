"""
GitMCP Task Framework: Atomic, composable, observable task execution.

This module provides a structured task execution system with:
  - Task decomposition (each function = one responsibility)
  - Task composition (pipeline chaining)
  - Built-in observability (metrics, logging, tracing)
  - Error standardization
  - Batch efficiency (parallel execution, backpressure)

Design:
  TaskContext  -> Encapsulates execution context (metrics, logging, config)
  TaskResult   -> Standardized result wrapper (data, status, errors)
  TaskHandler  -> Type-safe async function with auto-registration
  TaskPipeline -> Composes handlers into batched, parallelizable workflows
  TaskRegistry -> Central dispatch & schema management

Usage:
  @task_handler(name="gist:fetch")
  async def fetch_gist_task(context, gist_id: str) -> TaskResult:
      try:
          data = await fetch_from_api(gist_id)
          context.metrics.inc("gist.fetch.success")
          return TaskResult(data=data, status="complete")
      except Exception as e:
          context.metrics.inc("gist.fetch.error")
          raise TaskError(f"Failed to fetch gist {gist_id}: {e}")

  # Use in pipeline
  pipeline = TaskPipeline(
      tasks=["gist:fetch", "gist:parse", "gist:dedupe"],
      parallel_threshold=10
  )
  results = await pipeline.execute_batch(gist_ids)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Optional, TypeVar, Generic,
    Coroutine, Set, Tuple, Union
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ═════════════════════════════════════════════════════════════════════════
# Enums & Status Codes
# ═════════════════════════════════════════════════════════════════════════

class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


class TaskErrorCode(str, Enum):
    """Standard error codes for tasks."""
    VALIDATION_ERROR = "validation_error"
    AUTH_ERROR = "auth_error"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"


# ═════════════════════════════════════════════════════════════════════════
# Exceptions
# ═════════════════════════════════════════════════════════════════════════

class TaskError(Exception):
    """Base error for task execution."""

    def __init__(
        self,
        message: str,
        code: TaskErrorCode = TaskErrorCode.UNKNOWN_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        logger.error(f"TaskError: {code.value} - {message}", extra={"details": self.details})

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "code": self.code.value,
            "details": self.details,
        }


class TaskValidationError(TaskError):
    """Validation error during task execution."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, TaskErrorCode.VALIDATION_ERROR, details)


class TaskAuthError(TaskError):
    """Authentication error."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, TaskErrorCode.AUTH_ERROR, details)


class TaskNotFoundError(TaskError):
    """Resource not found error."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, TaskErrorCode.NOT_FOUND, details)


# ═════════════════════════════════════════════════════════════════════════
# Metrics Tracking
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class TaskMetrics:
    """Metrics collector for task execution."""

    counters: Dict[str, int] = field(default_factory=dict)
    timings: Dict[str, List[float]] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)

    def inc(self, key: str, value: int = 1) -> None:
        """Increment counter."""
        self.counters[key] = self.counters.get(key, 0) + value
        logger.debug(f"Metric counter {key} = {self.counters[key]}")

    def record_timing(self, key: str, duration_ms: float) -> None:
        """Record timing measurement."""
        if key not in self.timings:
            self.timings[key] = []
        self.timings[key].append(duration_ms)
        avg = sum(self.timings[key]) / len(self.timings[key])
        logger.debug(f"Metric timing {key}: {duration_ms:.1f}ms (avg: {avg:.1f}ms)")

    def set_gauge(self, key: str, value: float) -> None:
        """Set gauge value."""
        self.gauges[key] = value
        logger.debug(f"Metric gauge {key} = {value}")

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        timings_summary = {
            k: {
                "count": len(v),
                "min": min(v),
                "max": max(v),
                "avg": sum(v) / len(v),
            }
            for k, v in self.timings.items()
        }
        return {
            "counters": self.counters,
            "timings": timings_summary,
            "gauges": self.gauges,
        }


# ═════════════════════════════════════════════════════════════════════════
# Task Context (Encapsulates execution state)
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class TaskContext:
    """Execution context for a task.
    
    Provides access to:
      - Metrics tracking
      - Logging context
      - Configuration
      - Shared state (user tokens, cache, etc.)
    """

    task_name: str
    metrics: TaskMetrics = field(default_factory=TaskMetrics)
    config: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    parent_task: Optional[str] = None

    def get_elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        elapsed = datetime.now(timezone.utc) - self.started_at
        return elapsed.total_seconds() * 1000

    def log_debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        logger.debug(
            f"[{self.task_name}] {message}",
            extra={"context": self.task_name, **kwargs}
        )

    def log_info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        logger.info(
            f"[{self.task_name}] {message}",
            extra={"context": self.task_name, **kwargs}
        )

    def log_error(self, message: str, **kwargs) -> None:
        """Log error message with context."""
        logger.error(
            f"[{self.task_name}] {message}",
            extra={"context": self.task_name, **kwargs}
        )


# ═════════════════════════════════════════════════════════════════════════
# Task Result (Standardized output)
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class TaskResult(Generic[T]):
    """Standardized task result wrapper.
    
    Contains:
      - data: The actual result payload
      - status: Completion status
      - error_info: Error details (if failed)
      - metadata: Operation metadata (timing, retries, etc.)
    """

    data: Optional[T] = None
    status: TaskStatus = TaskStatus.PENDING
    error_info: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def success(
        data: T,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TaskResult[T]":
        """Create successful result."""
        return TaskResult(
            data=data,
            status=TaskStatus.COMPLETE,
            metadata=metadata or {},
        )

    @staticmethod
    def error(
        error: Union[TaskError, Exception],
        status: TaskStatus = TaskStatus.FAILED,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TaskResult":
        """Create error result."""
        if isinstance(error, TaskError):
            error_dict = error.to_dict()
        else:
            error_dict = {
                "error": error.__class__.__name__,
                "message": str(error),
                "code": "unknown_error",
            }
        return TaskResult(
            status=status,
            error_info=error_dict,
            metadata=metadata or {},
        )

    @staticmethod
    def retry(
        error: Exception,
        attempt: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TaskResult":
        """Create retry result."""
        m = metadata or {}
        m["attempt"] = attempt
        return TaskResult.error(error, TaskStatus.RETRY, m)

    def is_success(self) -> bool:
        """Check if result is successful."""
        return self.status == TaskStatus.COMPLETE

    def is_error(self) -> bool:
        """Check if result is error."""
        return self.status == TaskStatus.FAILED

    def is_retry(self) -> bool:
        """Check if result should retry."""
        return self.status == TaskStatus.RETRY

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "data": self.data,
            "status": self.status.value,
            "error": self.error_info,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════
# Task Handler Registration
# ═════════════════════════════════════════════════════════════════════════

TaskHandlerFunc = Callable[
    [TaskContext, ...], Coroutine[Any, Any, TaskResult]
]

_TASK_REGISTRY: Dict[str, TaskHandlerFunc] = {}
_TASK_SCHEMAS: Dict[str, Dict[str, Any]] = {}


def task_handler(
    name: str,
    schema: Optional[Dict[str, Any]] = None,
):
    """Decorator to register a task handler.
    
    Usage:
        @task_handler(name="gist:fetch", schema={...})
        async def fetch_gist_task(context, gist_id: str) -> TaskResult:
            ...
    """
    def decorator(func: TaskHandlerFunc) -> TaskHandlerFunc:
        _TASK_REGISTRY[name] = func
        _TASK_SCHEMAS[name] = schema or {}
        logger.info(f"Registered task handler: {name}")
        return func
    return decorator


def get_task_handler(name: str) -> Optional[TaskHandlerFunc]:
    """Get registered task handler."""
    return _TASK_REGISTRY.get(name)


def get_all_tasks() -> Dict[str, TaskHandlerFunc]:
    """Get all registered task handlers."""
    return dict(_TASK_REGISTRY)


def get_task_schema(name: str) -> Dict[str, Any]:
    """Get task schema for MCP export."""
    return _TASK_SCHEMAS.get(name, {})


# ═════════════════════════════════════════════════════════════════════════
# Task Pipeline (Orchestrator)
# ═════════════════════════════════════════════════════════════════════════

class TaskPipeline:
    """Orchestrates task composition and batch execution.
    
    Features:
      - Sequential or parallel task chaining
      - Parallel batch processing
      - Automatic input/output wiring
      - Error handling & recovery
      - Backpressure & rate limiting
    """

    def __init__(
        self,
        tasks: List[str],
        parallel_threshold: int = 10,
        max_concurrent: int = 5,
        timeout_per_task_s: float = 30.0,
    ):
        """Initialize pipeline.
        
        Args:
            tasks: List of task names (in execution order)
            parallel_threshold: If batch size >= this, parallelize
            max_concurrent: Max concurrent tasks
            timeout_per_task_s: Timeout per task
        """
        self.tasks = tasks
        self.parallel_threshold = parallel_threshold
        self.max_concurrent = max_concurrent
        self.timeout_per_task_s = timeout_per_task_s
        self.metrics = TaskMetrics()

    async def execute_single(
        self,
        task_name: str,
        context: TaskContext,
        **kwargs: Any,
    ) -> TaskResult:
        """Execute a single task."""
        handler = get_task_handler(task_name)
        if not handler:
            return TaskResult.error(
                TaskError(f"Task handler not found: {task_name}"),
                metadata={"task": task_name},
            )

        context.task_name = task_name
        start_time = time.time()
        try:
            logger.info(f"Executing task: {task_name} with kwargs: {list(kwargs.keys())}")
            result = await asyncio.wait_for(
                handler(context, **kwargs),
                timeout=self.timeout_per_task_s,
            )
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_timing(f"{task_name}.duration", duration_ms)
            self.metrics.inc(f"{task_name}.success")
            logger.info(f"Task {task_name} completed in {duration_ms:.1f}ms")
            return result
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.inc(f"{task_name}.timeout")
            logger.error(f"Task {task_name} timed out after {duration_ms:.1f}ms")
            return TaskResult.error(
                TaskError(
                    f"Task {task_name} timed out after {self.timeout_per_task_s}s",
                    TaskErrorCode.TIMEOUT,
                ),
                metadata={"task": task_name, "duration_ms": duration_ms},
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.inc(f"{task_name}.error")
            logger.error(f"Task {task_name} failed: {e}")
            return TaskResult.error(
                e,
                metadata={"task": task_name, "duration_ms": duration_ms},
            )

    async def execute_batch(
        self,
        items: List[Dict[str, Any]],
        context_factory: Optional[Callable[[], TaskContext]] = None,
    ) -> List[TaskResult]:
        """Execute pipeline on batch of items.
        
        Args:
            items: List of {task1_param: value, task2_param: value, ...}
            context_factory: Factory to create TaskContext per item
        
        Returns:
            List of TaskResults
        """
        if not context_factory:
            context_factory = lambda: TaskContext(task_name="batch")

        results = []

        # Decide: sequential or parallel based on batch size
        if len(items) >= self.parallel_threshold:
            logger.info(
                f"Batch size {len(items)} >= threshold {self.parallel_threshold}; "
                f"parallelizing with {self.max_concurrent} concurrent tasks"
            )
            results = await self._execute_batch_parallel(items, context_factory)
        else:
            logger.info(f"Batch size {len(items)} < threshold; executing sequentially")
            results = await self._execute_batch_sequential(items, context_factory)

        self.metrics.inc("batch.executed", len(items))
        self.metrics.inc("batch.success", sum(1 for r in results if r.is_success()))
        self.metrics.inc("batch.error", sum(1 for r in results if r.is_error()))

        return results

    async def _execute_batch_sequential(
        self,
        items: List[Dict[str, Any]],
        context_factory: Callable[[], TaskContext],
    ) -> List[TaskResult]:
        """Execute batch sequentially."""
        results = []
        for i, item in enumerate(items):
            context = context_factory()
            context.state["batch_index"] = i
            context.state["batch_total"] = len(items)

            # Execute all tasks in pipeline for this item
            pipeline_result = await self._execute_pipeline_for_item(item, context)
            results.append(pipeline_result)

        return results

    async def _execute_batch_parallel(
        self,
        items: List[Dict[str, Any]],
        context_factory: Callable[[], TaskContext],
    ) -> List[TaskResult]:
        """Execute batch with parallelization using semaphore."""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_item(i: int, item: Dict[str, Any]) -> TaskResult:
            async with semaphore:
                context = context_factory()
                context.state["batch_index"] = i
                context.state["batch_total"] = len(items)
                return await self._execute_pipeline_for_item(item, context)

        tasks = [
            process_item(i, item)
            for i, item in enumerate(items)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results

    async def _execute_pipeline_for_item(
        self,
        item: Dict[str, Any],
        context: TaskContext,
    ) -> TaskResult:
        """Execute all tasks in pipeline for a single item."""
        current_data = item
        
        for task_name in self.tasks:
            # Execute task with current_data as kwargs
            result = await self.execute_single(task_name, context, **current_data)
            
            if result.is_error():
                logger.error(f"Pipeline halted at {task_name}: {result.error}")
                return result
            
            # Chain: output of one task -> input to next
            current_data = result.data if result.data else current_data
        
        return TaskResult.success(current_data)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get pipeline metrics summary."""
        return self.metrics.get_summary()


# ═════════════════════════════════════════════════════════════════════════
# Export for typing
# ═════════════════════════════════════════════════════════════════════════

from typing import Union

__all__ = [
    "TaskStatus",
    "TaskErrorCode",
    "TaskError",
    "TaskValidationError",
    "TaskAuthError",
    "TaskNotFoundError",
    "TaskMetrics",
    "TaskContext",
    "TaskResult",
    "task_handler",
    "get_task_handler",
    "get_all_tasks",
    "get_task_schema",
    "TaskPipeline",
]
