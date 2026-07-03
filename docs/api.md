# API Reference

## CLI Commands

```
advancement [OPTIONS] COMMAND [ARGS]
```

### Options

| Option | Description |
|--------|-------------|
| `--config`, `-c PATH` | Path to config file |
| `--log-level TEXT` | Override log level |
| `--doctor` | Run self-check and exit |
| `--ai-mode` | Enable AI-native mode |
| `--version` | Show version |

### Commands

| Command | Description |
|---------|-------------|
| `run` | Start MCP server + skill agent |
| `serve` | WebSocket server (adaptive TLS/mTLS) |
| `temporal` | Temporal intelligence commands |
| `quarantine` | Manage quarantined plugins |
| `marketplace` | Plugin marketplace |
| `bridge` | MCP federation |
| `workflow` | DAG workflow composer |
| `schema` | Schema registry |
| `doctor` | Self-diagnostic |
| `config` | Show configuration |
| `agent [INTENT]` | Route intent through orchestrator |
| `mem-set` / `mem-get` | Memory operations |
| `mem-search` | Semantic memory search |
| `forget` / `undo` | Memory deletion and rollback |
| `compact` | Run memory compaction |
| `metrics` | Start Prometheus endpoint |
| `mtls-status` | Show mTLS config status |
| `build` | Run build pipeline |
| `verify` | Verify artifact checksum |

### Temporal Commands

```bash
# Record event
advancement temporal record "user_login" '{"user":"alice"}'

# Record with TTL (auto-expire after 1 hour)
advancement temporal record "error" '{"code":500}' --ttl 3600

# Forecast (next 24 hours)
advancement temporal forecast "user_login" --horizon 86400

# Schedule task (fire in 5 seconds)
advancement temporal schedule "alert" 5 --payload '{"severity":"high"}'

# Cancel scheduled task
advancement temporal cancel "schedule_id"

# View engine state
advancement temporal summary

# Resolve temporal dependencies
advancement temporal depends "login" "purchase" "payment"

# Export MCP tool definitions
advancement temporal tools

# Execute all due scheduled tasks
advancement temporal execute
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `advancement_doctor` | Full diagnostic JSON |
| `advancement_config` | Active configuration JSON |
| `advancement_force_health` | System resource health |
| `advancement_enhance_payload` | Payload transformation |
| `bridge_*` (9 tools) | Bridge federation operations |
| `workflow_*` (4 tools) | Workflow operations |
| `semantic_*` (5 tools) | Semantic search operations |
| `temporal_record_event` | Log timestamped events |
| `temporal_forecast` | Predict future occurrences |
| `temporal_schedule` | Schedule one-shot tasks |
| `temporal_cancel_schedule` | Cancel pending tasks |
| `temporal_summary` | Query engine state |

---

## MCP Resources

| URI | Description |
|-----|-------------|
| `advancement://config` | Config as JSON |
| `advancement://logs` | Last 100 log lines |
| `advancement://doctor` | Diagnostic report |

---

## Python API

### TemporalEngine

```python
from advancement_machine.temporal_engine import TemporalEngine

engine = TemporalEngine()

# Record event
event_id = engine.record_event("user_login", {"user": "alice"}, ttl=3600)

# Query events
events = engine.query_events("user_login")

# Forecast
forecast = engine.forecast("user_login", horizon=3600)
# Returns: {predicted_count, confidence, trend, avg_interval_seconds}

# Schedule task
schedule_id = engine.schedule_at("alert", 5, lambda d: print(d), {"msg": "hello"})

# Cancel schedule
engine.cancel_schedule(schedule_id)

# Execute due tasks (async)
import asyncio
executed = asyncio.run(engine.execute_scheduled())

# Export MCP tool definitions
tools = engine.get_tool_definitions()
```

### BuildSystem

```python
from advancement_machine.build_system import BuildSystem

builder = BuildSystem(source_dir="src")

# Build all artifacts
result = builder.build_all()

# Generate SBOM
sbom = builder.generate_sbom()
```

### SupplyChainValidator

```python
from advancement_machine.supply_chain import SupplyChainValidator

validator = SupplyChainValidator("sbom.json")

# Verify artifact checksums
is_valid = validator.verify_checksum("artifact.whl", "sha256:...")

# Check dependency freshness
results = validator.check_all_freshness()
```

### Circuit Breaker

```python
from advancement_machine.intel_mcp.circuit_breaker import get_breaker

breaker = get_breaker("gist:fetch_raw")
# States: CLOSED -> OPEN -> HALF_OPEN
```

### Rate Limiter

```python
from advancement_machine.intel_mcp.rate_limiter import get_global_limiter

limiter = get_global_limiter()
limiter.set_quota("user123", rps=10, burst=50)
```

### Request Tracer

```python
from advancement_machine.intel_mcp.request_tracer import RequestTracer

tracer = RequestTracer(request_id="uuid", user_id="user123")
tracer.log_info("Starting task", {"task": "fetch_raw"})
headers = tracer.get_headers_for_propagation()
```

### Task Registry

```python
import asyncio
from advancement_machine.intel_mcp.gitmcp_registry import get_global_registry
from advancement_machine.intel_mcp.task_framework import TaskContext

async def main():
    registry = await get_global_registry()

    # Single task execution
    context = TaskContext(task_name="gist:fetch_raw")
    result = await registry.execute("gist:fetch_raw", context, gist_id="abc123")
    print(f"Status: {result.status}")

    # Batch execution (parallel)
    requests = [("gist:fetch_raw", {"gist_id": f"gist_{i}"}) for i in range(10)]
    results = await registry.batch_execute(requests, context, max_concurrency=4)

asyncio.run(main())
```

---

## Error Handling

```python
from advancement_machine.errors import (
    ErrorResponse,
    ErrorCode,
    ValidationError,
    InsufficientDataError,
    ScheduleNotFoundError,
    EventNotFoundError,
    InvalidStateError,
    create_error_response,
)

# Create error response
error = create_error_response(
    code=ErrorCode.VALIDATION_ERROR,
    message="Invalid input",
    details={"field": "user_id"}
)
```
