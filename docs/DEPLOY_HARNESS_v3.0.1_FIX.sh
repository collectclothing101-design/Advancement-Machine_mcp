#!/bin/bash
# Deploy fixed Harness MCP v3.0.1 (resolves RequestContext import error)

set -e

MCP_DIR="${HOME}/Library/Application Support/AI-Tools/mcp"
CLAUDE_CONFIG="${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
VENV_PYTHON="${MCP_DIR}/.venv/bin/python"

echo "═════════════════════════════════════════════════════"
echo "Harness MCP v3.0.1 Deployment (Fixes RequestContext)"
echo "═════════════════════════════════════════════════════"
echo ""

# Step 1: Backup current server
if [ -f "${MCP_DIR}/harness_claude_advanced_mcp.py" ]; then
  echo "[1/4] Backing up old MCP server..."
  cp "${MCP_DIR}/harness_claude_advanced_mcp.py" \
     "${MCP_DIR}/harness_claude_advanced_mcp.py.backup.$(date +%Y%m%d-%H%M%S)"
  echo "✓ Backup created"
fi

# Step 2: Deploy fixed version
echo "[2/4] Deploying fixed MCP server v3.0.1..."
cat > "${MCP_DIR}/harness_claude_advanced_mcp.py" << 'MCP_EOF'
#!/usr/bin/env python3
"""
Harness Claude MCP Server - v3.0.1 (mcp 1.28.1 compatible)
Fixed RequestContext import issue
"""

import json
import sys
import logging
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
except ImportError as e:
    logger.error(f"Failed to import mcp: {e}")
    logger.error("Install mcp: pip install mcp")
    sys.exit(1)

# Create server instance
server = Server("harness")

# Define tools
TOOLS = [
    {
        "name": "help",
        "description": "Show available Harness commands",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "status",
        "description": "Get Harness installation status",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "config",
        "description": "Show Harness configuration",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name=tool["name"],
            description=tool["description"],
            inputSchema=tool["inputSchema"]
        )
        for tool in TOOLS
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "help":
        return [TextContent(
            type="text",
            text="""Harness v3.0.0 - Available Commands

help     - Show this help message
status   - Installation status and diagnostic info
config   - Display current configuration

MCP Server: harness_claude_advanced_mcp.py v3.0.1
"""
        )]
    
    elif name == "status":
        import os
        harness_dir = os.path.expanduser("~/Library/Application Support/AI-Tools/harness")
        mcp_dir = os.path.expanduser("~/Library/Application Support/AI-Tools/mcp")
        
        return [TextContent(
            type="text",
            text=f"""Harness Status:
✓ MCP Server: Running (v3.0.1)
✓ Python: {sys.version.split()[0]}

Directories:
  Harness: {harness_dir} (exists: {os.path.isdir(harness_dir)})
  MCP:     {mcp_dir} (exists: {os.path.isdir(mcp_dir)})

Claude Desktop Config:
  Location: ~/Library/Application Support/Claude/claude_desktop_config.json
"""
        )]
    
    elif name == "config":
        import os
        config_path = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
        
        try:
            with open(config_path) as f:
                config = json.load(f)
            harness_config = config.get("mcpServers", {}).get("harness", {})
            return [TextContent(
                type="text",
                text=f"""Claude Desktop Configuration:\n\n{json.dumps(harness_config, indent=2)}"""
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error reading config: {e}"
            )]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown command: {name}. Type 'help' for available commands"
        )]

async def main():
    """Main entry point"""
    logger.info("Starting Harness MCP Server v3.0.1")
    async with server:
        await server.wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
MCP_EOF

chmod +x "${MCP_DIR}/harness_claude_advanced_mcp.py"
echo "✓ MCP server deployed"

# Step 3: Test the fixed server
echo "[3/4] Testing fixed MCP server..."
"$VENV_PYTHON" -m py_compile "${MCP_DIR}/harness_claude_advanced_mcp.py"
echo "✓ Syntax check passed"

# Step 4: Verify Claude config uses venv Python
echo "[4/4] Verifying Claude Desktop config..."
"$VENV_PYTHON" << 'PYTHON_EOF'
import json
import os

config_path = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
venv_python = os.path.expanduser("~/Library/Application Support/AI-Tools/mcp/.venv/bin/python")
mcp_server = os.path.expanduser("~/Library/Application Support/AI-Tools/mcp/harness_claude_advanced_mcp.py")

try:
    with open(config_path, 'r') as f:
        raw = f.read().strip()
        config = json.loads(raw) if raw else {}
except:
    config = {}

if not isinstance(config, dict):
    config = {}

config.setdefault("mcpServers", {})
config["mcpServers"]["harness"] = {
    "command": venv_python,
    "args": [mcp_server],
    "env": {
        "PYTHONUNBUFFERED": "1",
        "HARNESS_HOME": os.path.expanduser("~/Library/Application Support/AI-Tools/harness")
    }
}

os.makedirs(os.path.dirname(config_path), exist_ok=True)
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"✓ Claude config updated")
print(f"  Command: {venv_python}")
print(f"  Server: {mcp_server}")
PYTHON_EOF

echo ""
echo "═════════════════════════════════════════════════════"
echo "DEPLOYMENT COMPLETE"
echo "═════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "1. Fully quit Claude Desktop"
echo "2. Reopen Claude Desktop"
echo "3. Check: Settings > Integrations > harness [Connected]"
echo "4. Test: Type '@harness help'"
echo ""
echo "If still not working:"
echo "  killall Claude && sleep 2 && open /Applications/Claude.app"
echo ""
