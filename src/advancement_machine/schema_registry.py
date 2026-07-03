"""
MCP Schema Registry — auto-generates OpenAPI 3.1, JSON Schema, and
MCP protocol definitions for every tool, resource, and prompt in the system.

Any AI client can fetch the full schema via a single tool call and
immediately understand the entire capability surface.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

from .mcp_server import TemporalMCPServer as AdvancementMCPServer
from .plugin_loader import PluginManager
try:
    from .force_multiplier import GoalDecomposer as ForceMultiplier
except ImportError:
    class ForceMultiplier:
        pass

logger = logging.getLogger(__name__)

SERVERS = {
    "advancement-ws": {
        "url": "ws://localhost:8765",
        "description": "WebSocket MCP endpoint (plain)",
    },
    "advancement-wss": {
        "url": "wss://localhost:8765",
        "description": "WebSocket MCP endpoint (TLS)",
    },
    "advancement-stdio": {
        "url": "stdio://advancement",
        "description": "Local stdin/stdout MCP endpoint",
    },
}

class SchemaRegistry:
    """Generates and serves an OpenAPI 3.1 schema describing every MCP tool,
    resource, and prompt in the Advancement Machine.

    Output can be consumed directly by:
      - AI agents using function-calling APIs (OpenAI, Anthropic, etc.)
      - API gateway tools (Kong, APISIX)
      - Documentation generators
      - Code generation for client SDKs
    """

    def __init__(self, mcp_server: Optional[AdvancementMCPServer] = None,
                 plugin_manager: Optional[PluginManager] = None,
                 fm: Optional[ForceMultiplier] = None):
        self.mcp_server = mcp_server
        self.plugin_manager = plugin_manager
        self.fm = fm or ForceMultiplier()

    def set_server(self, mcp_server: AdvancementMCPServer):
        self.mcp_server = mcp_server

    def set_plugin_manager(self, pm: PluginManager):
        self.plugin_manager = pm

    def generate_openapi(self) -> dict:
        """Generate a full OpenAPI 3.1 schema from the current server state.

        Maps MCP tools → OpenAPI paths, MCP resources → schema components,
        MCP prompts → x-mcp-prompt extensions.
        """
        schema = {
            "openapi": "3.1.0",
            "info": {
                "title": "Advancement Machine — MCP Engine",
                "version": "0.3.0",
                "description": (
                    "Universal MCP engine for AI agents. Provides tools, "
                    "resources, and prompts for software improvement, "
                    "plugin management, skill execution, system observation, "
                    "and multi-agent orchestration.\n\n"
                    "All MCP tools are exposed as OpenAPI operations. "
                    "Use the `list_tools` RPC or call any path directly."
                ),
                "x-mcp-protocol": "0.1.0",
                "x-generated-at": datetime.now(timezone.utc).isoformat(),
            },
            "servers": list(SERVERS.values()),
            "paths": self._build_paths(),
            "components": {
                "schemas": self._build_schemas(),
                "x-mcp-prompts": self._build_prompts(),
                "x-mcp-resources": self._build_resources(),
            },
            "x-mcp-capabilities": {
                "tools": {"listChanged": True},
                "resources": {"listChanged": True, "subscribe": True},
                "prompts": {"listChanged": True},
                "logging": {},
            },
            "x-agent-hints": {
                "preferred_model": "any",
                "tool_style": "function_calling",
                "resource_style": "uri_template",
                "prompt_style": "template",
                "authentication": "none",  # or "mtls"
            },
        }
        return schema

    def _build_paths(self) -> dict:
        """Convert MCP tools into OpenAPI paths.

        Standard RPC methods become /rpc/{method}.
        Each custom tool becomes /tools/{tool_name}.
        """
        paths = {}

        # Standard MCP RPC endpoints
        paths.update({
            "/rpc/initialize": {
                "post": {
                    "summary": "Initialize MCP session",
                    "operationId": "mcpInitialize",
                    "x-mcp-method": "initialize",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/McpInitializeRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Initialization result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/McpInitializeResponse"}
                                }
                            }
                        }
                    },
                    "x-agent-function": "Initialize the MCP session — call this first before any tool."
                }
            },
            "/rpc/list_tools": {
                "post": {
                    "summary": "List available tools",
                    "operationId": "mcpListTools",
                    "x-mcp-method": "list_tools",
                    "responses": {
                        "200": {
                            "description": "Tool definitions",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/McpToolList"}
                                }
                            }
                        }
                    },
                    "x-agent-function": "Discover all available tools and their input schemas."
                }
            },
            "/rpc/call_tool": {
                "post": {
                    "summary": "Execute a tool",
                    "operationId": "mcpCallTool",
                    "x-mcp-method": "call_tool",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/McpCallToolRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Tool execution result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/McpCallToolResponse"}
                                }
                            }
                        }
                    },
                    "x-agent-function": "Call any tool by name with its arguments."
                }
            },
            "/rpc/list_resources": {
                "post": {
                    "summary": "List available resources",
                    "operationId": "mcpListResources",
                    "x-mcp-method": "list_resources",
                    "responses": {
                        "200": {
                            "description": "Resource definitions",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/McpResourceList"}
                                }
                            }
                        }
                    },
                    "x-agent-function": "Discover all available resources and their URIs."
                }
            },
            "/rpc/read_resource": {
                "post": {
                    "summary": "Read a resource",
                    "operationId": "mcpReadResource",
                    "x-mcp-method": "read_resource",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/McpReadResourceRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Resource content",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/McpReadResourceResponse"}
                                }
                            }
                        }
                    },
                    "x-agent-function": "Read the content of any resource by URI."
                }
            },
            "/rpc/list_prompts": {
                "post": {
                    "summary": "List available prompts",
                    "operationId": "mcpListPrompts",
                    "x-mcp-method": "list_prompts",
                    "responses": {
                        "200": {
                            "description": "Prompt definitions"
                        }
                    },
                    "x-agent-function": "Discover all available prompt templates."
                }
            },
            "/rpc/get_prompt": {
                "post": {
                    "summary": "Get a prompt template",
                    "operationId": "mcpGetPrompt",
                    "x-mcp-method": "get_prompt",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "arguments": {"type": "object"}
                                    },
                                    "required": ["name"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Prompt messages"
                        }
                    },
                    "x-agent-function": "Retrieve a prompt template populated with arguments."
                }
            },
        })

        # Custom tool paths
        if self.mcp_server and hasattr(self.mcp_server, 'server') and self.mcp_server.server.tools:
            for tool in self.mcp_server.server.tools:
                tool_name = tool.name
                path_name = f"/tools/{tool_name}"
                paths[path_name] = {
                    "post": {
                        "summary": tool.description or f"Execute {tool_name}",
                        "operationId": f"tool_{tool_name}",
                        "x-mcp-tool": tool_name,
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": tool.inputSchema or {"type": "object", "properties": {}}
                                }
                            }
                        },
                        "responses": {
                            "200": {
                                "description": "Tool execution result",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "content": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "object",
                                                        "properties": {
                                                            "type": {"type": "string"},
                                                            "text": {"type": "string"}
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "x-agent-function": tool.description or f"Execute the {tool_name} tool.",
                    }
                }

        # Schema endpoint — the schema itself is a resource
        paths["/schema/openapi.json"] = {
            "get": {
                "summary": "Get the full OpenAPI schema for this MCP engine",
                "operationId": "getSchema",
                "responses": {
                    "200": {
                        "description": "OpenAPI 3.1 schema document",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                },
                "x-agent-function": (
                    "Fetch the complete OpenAPI schema describing every "
                    "MCP tool, resource, prompt, and capability. "
                    "Use this to understand the full surface of the engine."
                ),
            }
        }

        return paths

    def _build_schemas(self) -> dict:
        """Build JSON Schema definitions used by the API."""
        return {
            "McpInitializeRequest": {
                "type": "object",
                "properties": {
                    "protocol_version": {"type": "string", "default": "0.1.0"},
                    "capabilities": {"type": "object"},
                    "client_info": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": "string"}
                        }
                    }
                }
            },
            "McpInitializeResponse": {
                "type": "object",
                "properties": {
                    "protocol_version": {"type": "string"},
                    "server_name": {"type": "string"},
                    "server_version": {"type": "string"},
                    "capabilities": {"type": "object"}
                }
            },
            "McpToolList": {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "inputSchema": {"type": "object"}
                            }
                        }
                    }
                }
            },
            "McpCallToolRequest": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"}
                },
                "required": ["name"]
            },
            "McpCallToolResponse": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["text", "image", "resource"]},
                                "text": {"type": "string"},
                                "mimeType": {"type": "string"}
                            }
                        }
                    },
                    "isError": {"type": "boolean"}
                }
            },
            "McpResourceList": {
                "type": "object",
                "properties": {
                    "resources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "uri": {"type": "string"},
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "mimeType": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "McpReadResourceRequest": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string"}
                },
                "required": ["uri"]
            },
            "McpReadResourceResponse": {
                "type": "object",
                "properties": {
                    "contents": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "uri": {"type": "string"},
                                "mimeType": {"type": "string"},
                                "text": {"type": "string"}
                            }
                        }
                    }
                }
            },
        }

    def _build_prompts(self) -> list:
        """Extract prompts from the MCP server as schema components."""
        prompts = []
        if self.mcp_server and hasattr(self.mcp_server, 'server') and self.mcp_server.server.prompts:
            for prompt in self.mcp_server.server.prompts:
                entry = {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": prompt.arguments or [],
                    "x-mcp-usage": f"Call get_prompt with name='{prompt.name}' and arguments.",
                }
                prompts.append(entry)
        if not prompts:
            prompts.append({
                "name": "advancement_assess",
                "description": "Begin an assessment of the current system state",
                "arguments": [{"name": "scope", "description": "Scope (full, quick, custom)", "required": True}],
            })
        return prompts

    def _build_resources(self) -> list:
        """Extract resources from the MCP server as schema components."""
        resources = []
        if self.mcp_server and hasattr(self.mcp_server, 'server') and self.mcp_server.server.resources:
            for res in self.mcp_server.server.resources:
                resources.append({
                    "uri": res.uri,
                    "name": res.name,
                    "description": res.description,
                    "mimeType": res.mimeType,
                })
        if not resources:
            resources = [
                {"uri": "advancement://config", "name": "Active Configuration", "description": "Current configuration as JSON", "mimeType": "application/json"},
                {"uri": "advancement://logs", "name": "Application Logs", "description": "Tail of log file", "mimeType": "text/plain"},
                {"uri": "advancement://doctor", "name": "Doctor Report", "description": "Latest diagnostic report", "mimeType": "application/json"},
            ]
        return resources

    def save_schema(self, output_path: str = "schema/openapi.json") -> str:
        """Generate and save the OpenAPI schema to a file."""
        schema = self.generate_openapi()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(schema, f, indent=2)
        logger.info(f"OpenAPI schema saved to {path}")
        return str(path)

    def summary(self) -> dict:
        """Return a summary of the schema for quick agent consumption."""
        schema = self.generate_openapi()
        path_count = len(schema.get("paths", {}))
        return {
            "schema_url": "/schema/openapi.json",
            "total_tools": path_count,
            "servers": list(SERVERS.keys()),
            "capabilities": list(schema.get("x-mcp-capabilities", {}).keys()),
            "agent_hints": schema.get("x-agent-hints", {}),
            "generated_at": schema.get("info", {}).get("x-generated-at", ""),
        }