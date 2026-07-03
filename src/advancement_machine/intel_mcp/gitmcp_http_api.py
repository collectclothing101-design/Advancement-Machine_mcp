"""
GitMCP HTTP API Layer - Phase 2

Wraps the task registry in FastAPI endpoints with request/response handling,
error mapping, and structured logging.

Requires: FastAPI, Pydantic (added to imports, assumed available)
"""

from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime, timezone
import logging

from advancement_machine.intel_mcp.gitmcp_registry import (
    get_global_registry, TaskStatus
)
from advancement_machine.intel_mcp.task_framework import TaskContext

# Setup logging
logger = logging.getLogger("gitmcp.api")

# Initialize FastAPI app
app = FastAPI(
    title="GitMCP Task API",
    version="1.0.0",
    description="HTTP API for task-oriented Gist processing system"
)

# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    """Single task execution request."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_name": "gist:fetch_raw",
                "params": {"gist_id": "abc123"}
            }
        }
    )

    task_name: str = Field(..., description="Name of task to execute (e.g., 'gist:fetch_raw')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")


class TaskResponse(BaseModel):
    """Single task execution response."""
    request_id: str = Field(..., description="Unique request identifier for tracing")
    task_name: str = Field(..., description="Task that was executed")
    status: str = Field(..., description="Task status: success, error, retry")
    data: Optional[Dict[str, Any]] = Field(None, description="Result data (if successful)")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details (if failed)")
    elapsed_ms: int = Field(..., description="Execution time in milliseconds")


class BatchTasksRequest(BaseModel):
    """Batch task execution request."""
    tasks: List[TaskRequest] = Field(..., min_length=1, max_length=100, description="Tasks to execute")


class BatchTasksResponse(BaseModel):
    """Batch task execution response."""
    request_id: str = Field(..., description="Unique request identifier")
    submitted_at: str = Field(..., description="ISO 8601 timestamp")
    total: int = Field(..., description="Total tasks submitted")
    successful: int = Field(..., description="Count of successful tasks")
    failed: int = Field(..., description="Count of failed tasks")
    results: List[Dict[str, Any]] = Field(..., description="Individual task results")


class TaskListResponse(BaseModel):
    """List of available tasks."""
    total: int = Field(..., description="Number of available tasks")
    tasks: List[str] = Field(..., description="Task names")


class ToolListResponse(BaseModel):
    """List of available tasks in MCP tool format."""
    total: int = Field(..., description="Number of available tools")
    tools: List[Dict[str, Any]] = Field(..., description="MCP-formatted tool specifications")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field("healthy", description="Health status")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    registry_tasks: int = Field(..., description="Number of registered tasks")

# ─────────────────────────────────────────────────────────────────────────────
# Middleware & Context
# ─────────────────────────────────────────────────────────────────────────────

class RequestContext:
    """Request context with tracing & user info."""
    
    def __init__(self, request_id: str, user_id: str):
        self.request_id = request_id
        self.user_id = user_id
        self.started_at = datetime.now(timezone.utc)
    
    @staticmethod
    def from_request(request: Request) -> "RequestContext":
        """Extract context from HTTP request."""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        user_id = request.headers.get("X-User-ID", "anonymous")
        return RequestContext(request_id, user_id)
    
    def log_info(self, message: str):
        logger.info(f"[{self.request_id}] {message}")
    
    def log_error(self, message: str, error: Optional[Exception] = None):
        logger.error(f"[{self.request_id}] {message}", exc_info=error)
    
    def get_elapsed_ms(self) -> int:
        elapsed = datetime.now(timezone.utc) - self.started_at
        return int(elapsed.total_seconds() * 1000)


# ─────────────────────────────────────────────────────────────────────────────
# Health & Metadata Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    registry = await get_global_registry()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        registry_tasks=len(registry.tasks)
    )


@app.get("/api/v1/tasks", response_model=TaskListResponse, tags=["Metadata"])
async def list_tasks() -> TaskListResponse:
    """List all available tasks."""
    registry = await get_global_registry()
    return TaskListResponse(
        total=len(registry.tasks),
        tasks=sorted(registry.tasks.keys())
    )


@app.get("/api/v1/tools", response_model=ToolListResponse, tags=["Metadata"])
async def list_tools() -> ToolListResponse:
    """List all available tasks in MCP tool format."""
    registry = await get_global_registry()
    tools = registry.to_mcp_tools()
    return ToolListResponse(
        total=len(tools),
        tools=tools
    )


# ─────────────────────────────────────────────────────────────────────────────
# Single Task Execution
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/tasks/execute",
    response_model=TaskResponse,
    tags=["Task Execution"],
    responses={
        400: {"description": "Invalid request"},
        404: {"description": "Task not found"},
        500: {"description": "Internal server error"}
    }
)
async def execute_task(
    request: Request,
    task_request: TaskRequest,
    x_request_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None)
) -> TaskResponse:
    """
    Execute a single task synchronously.
    
    Returns:
    - request_id: Unique identifier for request tracing
    - status: Task execution status (success/error/retry)
    - data: Result data (if successful)
    - error: Error details (if failed)
    - elapsed_ms: Execution time
    """
    # Setup context
    ctx = RequestContext.from_request(request)
    ctx.log_info(f"Executing task: {task_request.task_name} with params: {task_request.params}")
    
    try:
        registry = await get_global_registry()
        
        # Validate task exists
        if task_request.task_name not in registry.tasks:
            ctx.log_error(f"Task not found: {task_request.task_name}")
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_request.task_name}' not found"
            )
        
        # Create task context
        task_context = TaskContext(task_name=task_request.task_name)
        
        # Execute task
        result = await registry.execute(
            task_request.task_name,
            task_context,
            **task_request.params
        )
        
        elapsed_ms = task_context.get_elapsed_ms()
        
        # Format response
        return TaskResponse(
            request_id=ctx.request_id,
            task_name=task_request.task_name,
            status=result.status.value,
            data=result.data,
            error=result.error_info,
            elapsed_ms=elapsed_ms
        )
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        ctx.log_error(f"Task execution failed: {str(e)}", e)
        raise HTTPException(
            status_code=500,
            detail=f"Task execution failed: {str(e)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Batch Task Execution
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/tasks/batch",
    response_model=BatchTasksResponse,
    tags=["Batch Execution"],
    responses={
        400: {"description": "Invalid request"},
        500: {"description": "Internal server error"}
    }
)
async def execute_batch(
    request: Request,
    batch_request: BatchTasksRequest,
    x_request_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None)
) -> BatchTasksResponse:
    """
    Execute multiple tasks in batch mode.
    
    Returns:
    - total: Number of tasks submitted
    - successful: Count of successful tasks
    - failed: Count of failed tasks
    - results: Individual task results (order preserved)
    """
    ctx = RequestContext.from_request(request)
    ctx.log_info(f"Batch executing {len(batch_request.tasks)} tasks")
    
    try:
        registry = await get_global_registry()
        results = []
        successful_count = 0
        failed_count = 0
        
        # Execute each task
        for task_req in batch_request.tasks:
            try:
                # Validate task exists
                if task_req.task_name not in registry.tasks:
                    results.append({
                        "task": task_req.task_name,
                        "status": "error",
                        "error": f"Task '{task_req.task_name}' not found"
                    })
                    failed_count += 1
                    continue
                
                # Create task context
                task_context = TaskContext(task_name=task_req.task_name)
                
                # Execute task
                result = await registry.execute(
                    task_req.task_name,
                    task_context,
                    **task_req.params
                )
                
                # Append result
                results.append({
                    "task": task_req.task_name,
                    "status": result.status.value,
                    "data": result.data,
                    "error": result.error_info,
                    "elapsed_ms": task_context.get_elapsed_ms()
                })
                
                if result.status == TaskStatus.SUCCESS:
                    successful_count += 1
                else:
                    failed_count += 1
            
            except Exception as e:
                ctx.log_error(f"Batch task failed: {task_req.task_name}: {str(e)}", e)
                results.append({
                    "task": task_req.task_name,
                    "status": "error",
                    "error": str(e)
                })
                failed_count += 1
        
        ctx.log_info(f"Batch complete: {successful_count} successful, {failed_count} failed")
        
        return BatchTasksResponse(
            request_id=ctx.request_id,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            total=len(batch_request.tasks),
            successful=successful_count,
            failed=failed_count,
            results=results
        )
    
    except Exception as e:
        ctx.log_error(f"Batch execution failed: {str(e)}", e)
        raise HTTPException(
            status_code=500,
            detail=f"Batch execution failed: {str(e)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with structured response."""
    return {
        "status": "error",
        "status_code": exc.status_code,
        "detail": exc.detail,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
    return {
        "status": "error",
        "status_code": 500,
        "detail": "Internal server error",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ─────────────────────────────────────────────────────────────────────────────
# App Event Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("GitMCP HTTP API starting up")
    registry = await get_global_registry()
    logger.info(f"Registry initialized with {len(registry.tasks)} tasks")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("GitMCP HTTP API shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# Utility: Run the app
# ─────────────────────────────────────────────────────────────────────────────

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the HTTP server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
