# API Reference


## CLI Commands

advancement [OPTIONS] COMMAND [ARGS]

Options: --config, -c PATH Path to config file --log-level TEXT Override log level --doctor Run self-check and exit --ai-mode Enable AI-native mode --version Show version

Commands: run Start MCP server + skill agent serve WebSocket server (adaptive TLS/mTLS) quarantine Manage quarantined plugins marketplace Plugin marketplace bridge MCP federation [--ai-mode] workflow DAG workflow composer [--ai-mode] schema Schema registry [--ai-mode] doctor Self-diagnostic config Show configuration agent [INTENT] Route intent through orchestrator mem-set / mem-get Memory operations mem-search Semantic memory search forget / undo Memory deletion and rollback compact Run memory compaction metrics Start Prometheus endpoint mtls-status Show mTLS config status build Run build pipeline verify Verify artifact checksum


## MCP Tools

| Tool | Description |
|---------------------------|-------------|
| advancement_doctor | Full diagnostic JSON |
| advancement_config | Active configuration JSON |
| advancement_force_health | System resource health |
| advancement_enhance_payload | Payload transformation |
| bridge_* (9 tools) | Bridge federation operations |
| workflow_* (4 tools) | Workflow operations |
| semantic_* (5 tools) | Semantic search operations |

## MCP Resources

| URI | Description |
|--------------------------|-------------|
| advancement://config | Config as JSON |
| advancement://logs | Last 100 log lines |
| advancement://doctor | Diagnostic report |

## Python Packages

### build_system
- `BuildSystem(source_dir)` — build pipeline
- `build_all(sign_key=None)` → `dict`
- `generate_sbom()` → `dict`

### supply_chain
- `SupplyChainValidator(sbom_path)` — verification
- `verify_checksum(artifact, sha256)` → `bool`
- `check_all_freshness()` → `list[dict]`

### developer_tools
- `hexdump(data, width=16)` → `str`
- `disassemble_x64(code, vma=0)` → `str`
- `shellcode_runner()` — context manager
- `binary_diff(a, b)` → `list[dict]`
- `NetworkPacket(src, dst, payload)` — packet crafting
- `stealth_toggles()` — anti-analysis context
- `ProcessSnapshot()` — state capture
- `Fuzzer(seed)` — mutation fuzzer