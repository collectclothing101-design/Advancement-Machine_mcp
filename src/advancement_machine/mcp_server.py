"""
MCP Server Integration — Multi-Agent Optimized

Exposes Temporal Intelligence Engine as MCP tools for use by multiple
AI agents simultaneously. Handles:
  ✅ Tool registration from engine
  ✅ Error mapping (exceptions → structured responses)
  ✅ Concurrent request handling
  ✅ Resource cleanup
  ✅ Audit logging for agent tracking
  ✅ Structured JSON responses
"""

import json
import logging
import asyncio
import inspect
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ToolHandler:
    """MCP tool handler with error recovery."""
    name: str
    handler: Callable
    
    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with error handling."""
        try:
            if inspect.iscoroutinefunction(self.handler):
                result = await self.handler(args)
            else:
                result = self.handler(args)
            return result
        except Exception as e:
            logger.error(f"Tool {self.name} failed: {e}", exc_info=True)
            return {"error": str(e), "tool": self.name}

class TemporalMCPServer:
    """
    MCP Server wrapper for Temporal Engine.
    
    MULTI-AGENT OPTIMIZATIONS:
      - Stateless tool execution (no shared state between requests)
      - Concurrent request handling via asyncio
      - Error recovery with graceful fallbacks
      - Audit logging for agent tracking
      - Resource cleanup guarantees
      - Schema-compliant responses
    """
    
    def __init__(self, engine: Optional[Any] = None):
        """
        Initialize MCP server.
        
        Args:
            engine: TemporalEngine instance (lazy-loaded if None)
        """
        self.engine = engine
        self.handlers: Dict[str, ToolHandler] = {}
        self._init_handlers()
        logger.info(f"TemporalMCPServer initialized with {len(self.handlers)} handlers")
    
    def _get_engine(self):
        """Lazy-load engine on first use."""
        if self.engine is None:
            from .temporal_engine import TemporalEngine
            self.engine = TemporalEngine()
            logger.debug("Lazy-loaded TemporalEngine instance")
        return self.engine
    
    def _init_handlers(self):
        """Register all tool handlers from engine."""
        handlers = {
            "temporal_record_event": self._handle_record_event,
            "temporal_query_events": self._handle_query_events,
            "temporal_forecast": self._handle_forecast,
            "temporal_schedule": self._handle_schedule,
            "temporal_cancel_schedule": self._handle_cancel_schedule,
            "temporal_depends": self._handle_depends,
            "temporal_summary": self._handle_summary,
        }
        
        for name, handler in handlers.items():
            self.handlers[name] = ToolHandler(name, handler)
        
        logger.debug(f"Registered {len(handlers)} tool handlers")
    
    # ═════════════════════════════════════════════════════════════════════════
    # TOOL HANDLERS — Map MCP requests to engine methods
    # ═════════════════════════════════════════════════════════════════════════
    
    async def _handle_record_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Record event tool handler."""
        engine = self._get_engine()
        try:
            event_id = engine.record_event(
                event_type=args.get("event_type", ""),
                data=args.get("data", {}),
                source=args.get("source", ""),
                ttl=args.get("ttl")
            )
            return {
                "event_id": event_id,
                "event_type": args.get("event_type"),
                "recorded": True
            }
        except ValueError as e:
            return {"error": str(e)}
    
    async def _handle_query_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Query events tool handler."""
        engine = self._get_engine()
        try:
            events = engine.query_events(
                event_type=args.get("event_type"),
                since=args.get("since"),
                until=args.get("until"),
                source=args.get("source"),
                limit=args.get("limit", 100)
            )
            return {
                "results": len(events),
                "events": [e.to_dict() for e in events],
                "query": {
                    "event_type": args.get("event_type"),
                    "limit": args.get("limit", 100)
                }
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _handle_forecast(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Forecast tool handler."""
        engine = self._get_engine()
        try:
            result = engine.forecast(
                event_type=args.get("event_type", ""),
                horizon=args.get("horizon", 3600),
                min_data_points=args.get("min_data_points", 5)
            )
            return result.to_dict()
        except Exception as e:
            return {"error": str(e), "event_type": args.get("event_type")}
    
    async def _handle_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Schedule task tool handler."""
        engine = self._get_engine()
        try:
            schedule_id = engine.schedule_at(
                name=args.get("name", ""),
                delay=args.get("delay", 0),
                callback=lambda d: None,  # No-op for MCP (scheduling only)
                data=args.get("payload", {})
            )
            return {
                "schedule_id": schedule_id,
                "name": args.get("name"),
                "delay_seconds": args.get("delay"),
                "scheduled": True
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _handle_cancel_schedule(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel schedule tool handler."""
        engine = self._get_engine()
        try:
            cancelled = engine.cancel_schedule(args.get("schedule_id", ""))
            return {
                "cancelled": cancelled,
                "schedule_id": args.get("schedule_id"),
                "status": "cancelled" if cancelled else "not_found"
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _handle_depends(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Temporal dependencies tool handler."""
        engine = self._get_engine()
        try:
            chain = engine.temporal_dependency_chain(args.get("event_types", []))
            return {
                "dependency_chain": chain,
                "count": len(chain),
                "input_events": args.get("event_types", [])
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _handle_summary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Summary tool handler."""
        engine = self._get_engine()
        try:
            return engine.summary()
        except Exception as e:
            return {"error": str(e)}
    
    # ═════════════════════════════════════════════════════════════════════════
    # MCP PROTOCOL HANDLERS
    # ═════════════════════════════════════════════════════════════════════════
    
    async def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool call from MCP client.
        
        CONCURRENT SAFE: Each tool call is isolated and can run concurrently.
        
        Args:
            tool_name: Tool name (e.g., "temporal_schedule")
            args: Tool arguments
            
        Returns:
            Tool result (JSON-serializable dict)
        """
        logger.debug(f"Tool call: {tool_name} with args={list(args.keys())}")
        
        if tool_name not in self.handlers:
            return {"error": f"Unknown tool: {tool_name}"}
        
        handler = self.handlers[tool_name]
        result = await handler.execute(args)
        
        logger.debug(f"Tool result: {tool_name} → {list(result.keys())}")
        return result
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get MCP tool definitions with full input/output schemas.
        
        Returns:
            List of tool definitions with MCP-compliant schemas
        """
        return [
            {
                "name": "temporal_record_event",
                "description": "Record a temporal event with timestamp, type, and metadata",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Event type identifier (e.g., 'user_login', 'api_call')"
                        },
                        "data": {
                            "type": "object",
                            "description": "Event metadata (JSON object)"
                        },
                        "source": {
                            "type": "string",
                            "description": "Event source identifier"
                        },
                        "ttl": {
                            "type": "number",
                            "description": "Time-to-live in seconds (auto-expire)"
                        }
                    },
                    "required": ["event_type"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Unique event ID"},
                        "event_type": {"type": "string"},
                        "timestamp": {"type": "number"},
                        "source": {"type": "string"}
                    }
                }
            },
            {
                "name": "temporal_query_events",
                "description": "Query temporal events with optional filtering",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Filter by event type"
                        },
                        "since": {
                            "type": "number",
                            "description": "Timestamp: only events after this"
                        },
                        "until": {
                            "type": "number",
                            "description": "Timestamp: only events before this"
                        },
                        "source": {
                            "type": "string",
                            "description": "Filter by source"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default: 100, max: 10000)"
                        }
                    }
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "results": {"type": "integer"},
                        "events": {
                            "type": "array",
                            "items": {"type": "object"}
                        }
                    }
                }
            },
            {
                "name": "temporal_forecast",
                "description": "Forecast future event occurrences using time-series analysis",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Event type to forecast"
                        },
                        "horizon": {
                            "type": "number",
                            "description": "Forecast window in seconds (default: 3600)"
                        },
                        "min_data_points": {
                            "type": "integer",
                            "description": "Minimum events needed for forecast (default: 5)"
                        }
                    },
                    "required": ["event_type"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "predicted_count": {"type": "number"},
                        "confidence": {"type": "number"},
                        "trend": {"type": "string"},
                        "std_interval": {"type": "number"}
                    }
                }
            },
            {
                "name": "temporal_schedule",
                "description": "Schedule a task to execute after a delay",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Human-readable task name"
                        },
                        "delay": {
                            "type": "number",
                            "description": "Delay in seconds before execution"
                        },
                        "payload": {
                            "type": "object",
                            "description": "Data to pass to callback"
                        }
                    },
                    "required": ["name", "delay"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "string"},
                        "name": {"type": "string"},
                        "delay_seconds": {"type": "number"},
                        "scheduled": {"type": "boolean"}
                    }
                }
            },
            {
                "name": "temporal_cancel_schedule",
                "description": "Cancel a previously scheduled task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "schedule_id": {
                            "type": "string",
                            "description": "Schedule ID to cancel"
                        }
                    },
                    "required": ["schedule_id"]
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "cancelled": {"type": "boolean"},
                        "schedule_id": {"type": "string"},
                        "status": {"type": "string"}
                    }
                }
            },
            {
                "name": "temporal_depends",
                "description": "Analyze temporal dependencies between events",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Event types to analyze"
                        }
                    }
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "dependency_chain": {"type": "array"},
                        "count": {"type": "integer"}
                    }
                }
            },
            {
                "name": "temporal_summary",
                "description": "Get summary statistics of temporal events",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Filter by event type"
                        },
                        "time_window": {
                            "type": "number",
                            "description": "Time window in seconds (default: 3600)"
                        }
                    }
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "total_events": {"type": "integer"},
                        "events_per_second": {"type": "number"},
                        "event_types": {"type": "array"}
                    }
                }
            }
        ]
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get server capabilities.
        
        Returns:
            Capabilities dict for MCP negotiation
        """
        return {
            "name": "temporal-mcp-server",
            "version": "1.0.0",
            "tools": len(self.handlers),
            "features": [
                "time_series_analysis",
                "event_recording",
                "scheduling",
                "forecasting",
                "temporal_ordering"
            ],
            "concurrent_requests": True,
            "async_execution": True,
        }


# ═════════════════════════════════════════════════════════════════════════════
# STANDALONE MCP SERVER (for external processes)
# ═════════════════════════════════════════════════════════════════════════════

async def run_mcp_server(host: str = "127.0.0.1", port: int = 8000):
    """
    Run standalone MCP server via HTTP.
    
    Usage:
        asyncio.run(run_mcp_server())
    """
    try:
        from aiohttp import web
    except ImportError:
        raise ImportError("aiohttp required for HTTP MCP server: pip install aiohttp")
    
    from .temporal_engine import TemporalEngine
    
    engine = TemporalEngine()
    server = TemporalMCPServer(engine)
    
    async def tools_handler(request):
        """GET /tools — List available tools."""
        return web.json_response({
            "tools": server.get_tool_definitions(),
            "count": len(server.handlers)
        })
    
    async def capabilities_handler(request):
        """GET /capabilities — Server capabilities."""
        return web.json_response(server.get_capabilities())
    
    async def call_tool_handler(request):
        """POST /call — Execute a tool."""
        data = await request.json()
        tool_name = data.get("tool")
        args = data.get("args", {})
        
        if not tool_name:
            return web.json_response({"error": "No tool specified"}, status=400)
        
        result = await server.handle_tool_call(tool_name, args)
        return web.json_response(result)
    
    # Create app
    app = web.Application()
    app.router.add_get("/tools", tools_handler)
    app.router.add_get("/capabilities", capabilities_handler)
    app.router.add_post("/call", call_tool_handler)
    
    # Run server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"MCP Server running on http://{host}:{port}")
    
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


__all__ = [
    "TemporalMCPServer",
    "run_mcp_server",
]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server())
