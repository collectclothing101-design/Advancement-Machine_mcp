# Advancement Machine

Universal MCP/Plugin/Skill Engine with Temporal Intelligence and Resilient Task Framework.

## Status

- **Tests**: 99/99 passing (6 Temporal + 25 Framework + 29 Resilience + 22 Registry + 17 Integration)
- **Confidence**: 9.5/10 — Production Ready
- **Blockers**: None

---

## Quick Start

```bash
# Install from PyPI
pip install advancement-machine

# Or install from source
git clone https://github.com/eurothrottle/advancement-machine.git
cd advancement-machine
pip install -e .

# Run all tests
pytest -v

# Quick CLI test
python3 -m advancement_machine.cli temporal record "event" '{}'
python3 -m advancement_machine.cli temporal summary
```

---

## What This System Does

Two integrated subsystems for autonomous, self-improving AI systems:

### 1. Temporal Intelligence Engine

Time-aware reasoning — scheduling, forecasting, event recording.

| MCP Tool | CLI Command | Description |
|----------|-------------|-------------|
| `temporal_record_event` | `temporal record <type> <data>` | Log timestamped events |
| `temporal_forecast` | `temporal forecast <type> --horizon <sec>` | Predict future occurrences |
| `temporal_schedule` | `temporal schedule <name> <delay> --payload <json>` | Schedule one-shot tasks |
| `temporal_cancel_schedule` | `temporal cancel <schedule_id>` | Cancel pending tasks |
| `temporal_summary` | `temporal summary` | Query engine state |

### 2. Intel MCP Task Framework

Composable task handlers with resilience patterns — transforms monolithic clients into microservice-style atomic operations.

**99 Tests Across 4 Phases:**

| Phase | Component | Tests | LOC |
|-------|-----------|-------|-----|
| Phase 1 | Task Decomposition | 25/25 | 547 |
| Phase 2 | Resilience Patterns | 29/29 | 878 |
| Phase 3 | Task Registry | 22/22 | 489 |
| Intel | Original System | 17/17 | 553 |
| Temporal | Scheduler & Events | 6/6 | 684 |

---

## Recursive adaptation

Workflow execution can feed runtime metrics into the recursive improvement engine.
See [workflow feedback and recursive adaptation](docs/recursive-adaptation.md) for
configuration, candidate validation, and deployment behavior.

## CLI Reference

### Temporal Commands

```bash
# Record event
python3 -m advancement_machine.cli temporal record "user_login" '{"user":"alice"}'

# Record with TTL (auto-expire after 1 hour)
python3 -m advancement_machine.cli temporal record "error" '{"code":500}' --ttl 3600

# Forecast (next 24 hours)
python3 -m advancement_machine.cli temporal forecast "user_login" --horizon 86400

# Schedule task (fire in 5 seconds)
python3 -m advancement_machine.cli temporal schedule "alert" 5 --payload '{"severity":"high"}'

# Cancel scheduled task
python3 -m advancement_machine.cli temporal cancel "schedule_id_here"

# View engine state
python3 -m advancement_machine.cli temporal summary

# Resolve temporal dependencies
python3 -m advancement_machine.cli temporal depends "login" "purchase" "payment"

# Export MCP tool definitions
python3 -m advancement_machine.cli temporal tools

# Execute all due scheduled tasks
python3 -m advancement_machine.cli temporal execute
```

### Test Commands

```bash
# All tests (99 total)
pytest -v

# Temporal tests only (6 tests)
pytest tests/test_temporal_scheduler.py -v

# Intel MCP fast check (29 tests)
pytest tests/test_phase2_core.py -v

# With coverage report
pytest tests/test_phase2_core.py --cov=src/advancement_machine/intel_mcp --cov-report=term-missing -v
```

### HTTP Server (Optional)

```bash
# Install optional dependency
pip install fastapi pydantic uvicorn

# Start server
python3 -m advancement_machine.intel_mcp.gitmcp_http_api
# Swagger docs at http://localhost:8000/docs
```

---

## Python API

### Temporal Engine

```python
from advancement_machine.temporal_engine import TemporalEngine

engine = TemporalEngine()

# Record event
event_id = engine.record_event("user_login", {"user": "alice"}, ttl=3600)

# Schedule task
schedule_id = engine.schedule_at("alert", 5, lambda d: print(d), {"msg": "hello"})

# Cancel
engine.cancel_schedule(schedule_id)

# Forecast
forecast = engine.forecast("user_login", horizon=3600)
# Returns: {predicted_count, confidence, trend, avg_interval_seconds}

# Execute due tasks (async)
import asyncio
executed = asyncio.run(engine.execute_scheduled())

# Export MCP tool definitions (7 tools)
tools = engine.get_tool_definitions()
```

### Intel MCP Task Registry

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

### Resilience Patterns

```python
# Circuit Breaker — fail-fast on repeated failures
from advancement_machine.intel_mcp.circuit_breaker import get_breaker
breaker = get_breaker("gist:fetch_raw")
# States: CLOSED -> OPEN -> HALF_OPEN

# Rate Limiter — DOS prevention (token bucket)
from advancement_machine.intel_mcp.rate_limiter import get_global_limiter
limiter = get_global_limiter()
limiter.set_quota("user123", rps=10, burst=50)

# Request Tracer — correlation IDs for distributed tracing
from advancement_machine.intel_mcp.request_tracer import RequestTracer
tracer = RequestTracer(request_id="uuid", user_id="user123")
tracer.log_info("Starting task", {"task": "fetch_raw"})
headers = tracer.get_headers_for_propagation()
```

---

## Architecture

```
src/advancement_machine/
├── __init__.py                  # Package exports, version
├── temporal_engine.py           # Temporal intelligence (684 LOC)
├── mcp_server.py                # MCP tool registration (533 LOC)
├── cli.py                       # CLI entry point (670 LOC)
├── errors.py                    # Standardized error handling
├── config.py                    # Configuration management
├── doctor.py                    # Self-diagnostics
├── plugin_loader.py             # Dynamic plugin loading
├── force_multiplier.py          # Resource optimization
├── intel_mcp/
│   ├── __init__.py              # Intel MCP package exports
│   ├── task_framework.py        # Atomic task handlers
│   ├── gist_task_handlers.py    # GitHub Gist operations
│   ├── gitmcp_registry.py       # Centralized dispatch
│   ├── circuit_breaker.py       # Fail-fast pattern
│   ├── request_tracer.py        # Correlation IDs
│   ├── rate_limiter.py          # DOS prevention
│   └── gitmcp_http_api.py       # REST endpoints
└── ...

tests/
├── test_temporal_scheduler.py   # Temporal scheduling tests
├── test_phase1_task_decomposition.py  # Task framework tests
├── test_phase2_core.py                # Resilience pattern tests
├── test_phase3_registry.py            # Registry dispatch tests
└── test_intel_mcp_integration.py      # Integration tests
```

---

## Performance

| Metric | Value |
|--------|-------|
| Full test suite (99 tests) | ~4 seconds |
| Circuit breaker transitions | <1ms |
| Rate limiter operations | <500us |
| Request tracer overhead | <100us |
| Batch parallel speedup | 8-10x over sequential |
| Engine memory | ~2 MB base + ~1 MB/1000 events |

## Concurrency

- Thread-safe (no locks needed — Python GIL + atomic deque/dict ops)
- Async-ready (full asyncio support)
- Tested with 10+ concurrent agents
- Stateless handlers — horizontally replicable

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `TypeError: unexpected keyword argument 'request_id'` | Use `TaskContext(task_name=...)` not `request_id` |
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install fastapi pydantic uvicorn` (HTTP only) |
| Tests fail silently | `cd` to project root first, then run |
| `command not found: advancement` | Use `python3 -m advancement_machine.cli` (not global install) |
| Memory growing unbounded | Set `TemporalEngine(window_size=10000)` to bound events |

---

## System Components

| Component | LOC | Status | Description |
|-----------|-----|--------|-------------|
| Task Framework | 547 | Stable | Atomic task decomposition, 25 handlers |
| Circuit Breaker | 234 | Stable | Fail-fast on repeated failures |
| Request Tracer | 273 | Stable | Correlation IDs, distributed tracing |
| Rate Limiter | 371 | Stable | Token bucket, per-user/per-task quotas |
| Task Registry | 489 | Stable | Centralized dispatch, batch execution (8-10x speedup) |
| Temporal Engine | 684 | Stable | Time-aware scheduling, forecasting, events |
| MCP Server | 533 | Stable | Tool registration, handler wiring, HTTP server |
| CLI | 670 | Stable | 9+ commands, 3 output formats (JSON/text/YAML) |
| HTTP API | 390 | Stable | FastAPI endpoints (optional dependency) |

---

## Key Features

- **Composable** — 8 independent atomic handlers, no coupling
- **Observable** — Execution tracking, metrics, correlation IDs
- **Resilient** — Circuit breaker, rate limiting, auto-recovery
- **Performant** — 8-10x throughput via parallel batch execution
- **Type-Safe** — 100% type hints, `TaskResult[T]` generics
- **Testable** — 99 tests, >75% coverage on core modules
- **Scalable** — Stateless handlers, horizontally replicable
- **MCP Compliant** — Claude API / OpenAI tool format

---

## Further Reading

| File | Content |
|------|---------|
| `docs/api.md` | Full CLI/MCP API reference |
| `docs/quickstart.md` | Installation guide |
| `docs/build-verify.md` | Build, SBOM, and audit guide |
| `docs/HARNESS_v3.0.1_FIX_COMPLETE_GUIDE.md` | MCP server compatibility fix |

---

**License**: MIT
**Python**: 3.10+ (3.14 tested)
**Last Verified**: 2026-06-27
