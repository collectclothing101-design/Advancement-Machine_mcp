# Documentation Index

All essential information is consolidated in **README.md**.

## Quick Navigation

| Need | Read |
|------|------|
| Getting started | `README.md` — Quick Start section |
| All commands | `README.md` — CLI Reference section |
| Python API | `README.md` — Python API section |
| Architecture | `README.md` — Architecture section |
| Troubleshooting | `README.md` — Troubleshooting section |
| Performance data | `README.md` — Performance section |
| Full API reference | `docs/api.md` |
| Installation | `docs/quickstart.md` |
| Build/test/SBOM | `docs/build-verify.md` |
| MCP v3.0.1 fix | `docs/HARNESS_v3.0.1_FIX_COMPLETE_GUIDE.md` |
| Quality checklist | `docs/CHECKLIST.md` |

## Source Code

| File | Purpose |
|------|---------|
| `src/advancement_machine/__init__.py` | Package exports, version |
| `src/advancement_machine/temporal_engine.py` | Temporal intelligence (scheduling, forecasting, events) |
| `src/advancement_machine/mcp_server.py` | MCP tool registration and handlers |
| `src/advancement_machine/cli.py` | CLI commands (temporal, config, agent) |
| `src/advancement_machine/errors.py` | Standardized error handling |
| `src/advancement_machine/config.py` | Configuration management |
| `src/advancement_machine/build_system.py` | Build pipeline and SBOM generation |
| `src/advancement_machine/intel_mcp/__init__.py` | Intel MCP package exports |
| `src/advancement_machine/intel_mcp/task_framework.py` | Atomic task decomposition |
| `src/advancement_machine/intel_mcp/gitmcp_registry.py` | Centralized task dispatch |
| `src/advancement_machine/intel_mcp/circuit_breaker.py` | Fail-fast pattern |
| `src/advancement_machine/intel_mcp/rate_limiter.py` | Token bucket rate limiting |
| `src/advancement_machine/intel_mcp/request_tracer.py` | Correlation ID tracing |
| `src/advancement_machine/intel_mcp/gitmcp_http_api.py` | FastAPI REST endpoints |

## Tests

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/test_temporal_scheduler.py` | 6 | Temporal scheduling, cancellation, callbacks |
| `tests/test_phase1_task_decomposition.py` | 25 | Task framework, metrics, pipelines |
| `tests/test_phase2_core.py` | 29 | Circuit breaker, rate limiter, tracer |
| `tests/test_phase3_registry.py` | 22 | Registry dispatch, batch execution, schemas |
| `tests/test_intel_mcp_integration.py` | 17 | End-to-end integration |

## Configuration

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, tool config |
| `setup.py` | Legacy editable install shim |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `.gitignore` | Git ignore rules |
| `grafana/advancement_dashboard.json` | Monitoring dashboard |
