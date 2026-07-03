# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-06-27

### Added
- Temporal Intelligence Engine with event recording, forecasting, and scheduling
- Intel MCP Task Framework with composable task handlers
- Circuit Breaker pattern for fail-fast error handling
- Rate Limiter with token bucket algorithm
- Request Tracer for distributed tracing with correlation IDs
- Task Registry for centralized dispatch and batch execution
- MCP Server with tool registration and HTTP API
- CLI interface with 9+ commands and 3 output formats
- SBOM generation for supply chain compliance
- Build system with wheel/sdist packaging

### Changed
- Migrated from legacy setup.py to pyproject.toml
- Updated MCP library compatibility to v1.28.1
- Improved test coverage to 99 tests

## [0.3.0] - 2024-01-01

### Added
- Initial release with core MCP server functionality
- Plugin loader system
- Configuration management
- Developer tools (hexdump, disassembly, binary diff)

## [0.2.0] - 2023-06-01

### Added
- Basic MCP protocol support
- CLI interface

## [0.1.0] - 2023-01-01

### Added
- Project scaffolding and initial setup
