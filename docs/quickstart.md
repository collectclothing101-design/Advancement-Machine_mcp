# Quickstart Guide

## Installation

### Method 1: PyPI

```bash
pip install advancement-machine
```

### Method 2: From Source

```bash
git clone https://github.com/eurothrottle/advancement-machine.git
cd advancement-machine
pip install -e .
```

### Method 3: With Optional Dependencies

```bash
# With HTTP server support (FastAPI)
pip install advancement-machine[http]

# With development tools (pytest, black, ruff, mypy)
pip install advancement-machine[dev]
```

## Verify Installation

```bash
# Check version
advancement --version

# Run self-diagnostics
advancement doctor
```

## Quick Start

```bash
# Record a temporal event
python3 -m advancement_machine.cli temporal record "user_login" '{"user":"alice"}'

# Query events
python3 -m advancement_machine.cli temporal summary

# Start MCP server
advancement run
```

## Next Steps

- [API Reference](api.md) - Full CLI and Python API documentation
- [Build & Verify Guide](build-verify.md) - Build, test, and SBOM generation
- [README](../README.md) - Architecture and detailed usage
