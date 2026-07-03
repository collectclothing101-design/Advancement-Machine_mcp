"""
CLI entry point for Advancement Machine.

Commands:
  - doctor: Run self-diagnostic
  - config: Show configuration
  - checklist: Run comprehensive quality checklist
  - agent: Route intent through orchestrator
  - temporal: Temporal intelligence engine (schedule, forecast, query events)
"""

import sys
import json
import time
import asyncio
import click
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from . import __app_name__, __version__
from .config import ConfigManager
from .doctor import Doctor
from .checklist import run_all_checkers, print_report
from .logging import setup_logging
from .temporal_engine import TemporalEngine
from .errors import ErrorResponse, ErrorCode, create_error_response

logger = setup_logging()

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL STATE: Single engine instance for CLI lifetime
# ═══════════════════════════════════════════════════════════════════════════════
_engine: Optional[TemporalEngine] = None

def get_engine() -> TemporalEngine:
    """Get or create the global temporal engine instance."""
    global _engine
    if _engine is None:
        _engine = TemporalEngine()
    return _engine

def format_output(data: Any, format_type: str = "json", pretty: bool = True) -> str:
    """Format output in specified format (JSON, YAML, or text)."""
    if format_type == "json":
        if pretty:
            return json.dumps(data, indent=2, default=str)
        return json.dumps(data, default=str)
    elif format_type == "text":
        return _format_text(data)
    elif format_type == "yaml":
        try:
            import yaml
            return yaml.dump(data, default_flow_style=False)
        except ImportError:
            logger.warning("PyYAML not installed, falling back to JSON")
            return json.dumps(data, indent=2, default=str)
    return json.dumps(data, indent=2, default=str)

def _format_text(data: Any, indent: int = 0) -> str:
    """Convert data to human-readable text format."""
    prefix = "  " * indent
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{prefix}{k}:")
                lines.append(_format_text(v, indent + 1))
            else:
                lines.append(f"{prefix}{k}: {v}")
        return "\n".join(lines)
    elif isinstance(data, list):
        lines = []
        for i, item in enumerate(data):
            lines.append(f"{prefix}[{i}]:")
            lines.append(_format_text(item, indent + 1))
        return "\n".join(lines)
    else:
        return f"{prefix}{data}"

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CLI GROUP
# ═══════════════════════════════════════════════════════════════════════════════

@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version")
@click.option("--config", "-c", type=click.Path(), help="Config file path")
@click.option("--format", "-f", type=click.Choice(["json", "text", "yaml"]), 
              default="json", help="Output format")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def cli(ctx, version, config, format, verbose):
    """Advancement Machine — Universal MCP/Plugin/Skill Engine
    
    TEMPORAL INTELLIGENCE MODULE:
    Schedule tasks, record events, forecast occurrences, and resolve temporal dependencies.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Store format in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["format"] = format
    ctx.obj["verbose"] = verbose
    
    if version:
        click.echo(f"{__app_name__} v{__version__}")
        sys.exit(0)
    
    if config:
        # Load config from file (implementation depends on ConfigManager)
        pass
    
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
@click.pass_context
def doctor(ctx):
    """Run self-diagnostic and report system health."""
    d = Doctor()
    report = d.run()
    output = format_output(report, ctx.obj["format"])
    click.echo(output)

@cli.command()
@click.pass_context
def config(ctx):
    """Show active configuration."""
    cfg = ConfigManager.get()
    output = format_output(cfg.model_dump(), ctx.obj["format"])
    click.echo(output)

@cli.command()
def checklist():
    """Run comprehensive quality checklist."""
    results = run_all_checkers()
    print_report(results)

@cli.command()
@click.argument("intent", required=False)
def agent(intent):
    """Route an intent through the agent orchestrator."""
    if not intent:
        click.echo("usage: advancement agent <intent>")
        sys.exit(1)
    
    # Placeholder: would require AsyncIO and orchestrator setup
    click.echo(f"Intent: {intent}")
    click.echo("(Agent routing not yet implemented in CLI)")

@cli.command()
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json",
              help="Output format")
def mem_search(format):
    """Search memory store (placeholder)."""
    click.echo("Memory search not yet implemented")

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL COMMAND GROUP — MAIN INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group(invoke_without_command=True)
@click.pass_context
def temporal(ctx):
    """
    Temporal Intelligence Engine — Schedule, Forecast, and Query Events
    
    EXAMPLES:
    
      Record an event:
        advancement temporal record "user_login" '{"user":"alice","ip":"192.168.1.1"}'
      
      Schedule a task:
        advancement temporal schedule "send_alert" 5 --payload '{"severity":"high"}'
      
      Forecast event occurrences:
        advancement temporal forecast "user_login" --horizon 3600
      
      Query historical events:
        advancement temporal query "user_login" --limit 10
      
      Resolve temporal dependencies:
        advancement temporal depends "login" "checkout" "payment_received"
      
      View engine state:
        advancement temporal summary
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: RECORD EVENT
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("event_type")
@click.argument("data", default="{}")
@click.option("--source", "-s", default="", help="Event source identifier")
@click.option("--ttl", "-t", type=float, default=None, help="Time-to-live in seconds")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def record(ctx, event_type, data, source, ttl, format, verbose):
    """
    Record a temporal event with current timestamp.
    
    EXAMPLES:
    
      Record a login event:
        advancement temporal record "user_login" '{"user":"alice","ip":"192.168.1.1"}'
      
      Record with TTL (auto-expire after 1 hour):
        advancement temporal record "api_request" '{"endpoint":"/v1/users"}' --ttl 3600
      
      Record with source tracking:
        advancement temporal record "error" '{"code":500}' --source "production-server-1"
    """
    engine = get_engine()
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        error = create_error_response(
            code=ErrorCode.INVALID_FORMAT,
            message="Invalid JSON format",
            details={"input": data, "parse_error": str(e)}
        )
        click.echo(format_output(error, format), err=True)
        sys.exit(1)
    
    try:
        event_id = engine.record_event(event_type, parsed, source, ttl)
        result = {
            "event_id": event_id,
            "event_type": event_type,
            "source": source or "(internal)",
            "ttl_seconds": ttl,
            "recorded": True
        }
        
        if verbose:
            result["data"] = parsed
            result["timestamp"] = time.time()
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = create_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to record event",
            details={"event_type": event_type},
            exception=e
        )
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: QUERY EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("event_type", required=False)
@click.option("--since", type=float, default=None, help="Query events since timestamp")
@click.option("--until", type=float, default=None, help="Query events until timestamp")
@click.option("--source", "-s", default=None, help="Filter by source")
@click.option("--limit", "-l", type=int, default=100, help="Max results")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.option("--verbose", "-v", is_flag=True, help="Show event details")
@click.pass_context
def query(ctx, event_type, since, until, source, limit, format, verbose):
    """
    Query recorded events with optional filters.
    
    EXAMPLES:
    
      Get all login events:
        advancement temporal query "user_login"
      
      Get last 5 events:
        advancement temporal query --limit 5
      
      Get events from specific source:
        advancement temporal query "error" --source "production-server-1"
      
      Get events from last hour:
        advancement temporal query --since $(date -d '1 hour ago' +%s)
    """
    engine = get_engine()
    try:
        events = engine.query_events(event_type, since, until, source, limit)
        
        if not events:
            result = {
                "query": {
                    "event_type": event_type,
                    "filters": {
                        "since": since,
                        "until": until,
                        "source": source,
                        "limit": limit
                    },
                    "results": 0,
                    "events": []
                }
            }
        else:
            events_data = []
            for e in events:
                event_dict = {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "source": e.source or "(internal)",
                    "ttl": e.ttl
                }
                if verbose:
                    event_dict["data"] = e.data
                events_data.append(event_dict)
            
            result = {
                "query": {
                    "event_type": event_type,
                    "filters": {
                        "since": since,
                        "until": until,
                        "source": source,
                        "limit": limit
                    },
                    "results": len(events_data),
                    "events": events_data
                }
            }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e)}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: FORECAST
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("event_type")
@click.option("--horizon", "-h", type=float, default=3600, help="Forecast horizon in seconds")
@click.option("--min-points", type=int, default=5, help="Minimum data points required")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def forecast(ctx, event_type, horizon, min_points, format):
    """
    Forecast future occurrences of an event type using statistical analysis.
    
    EXAMPLES:
    
      Forecast logins for next hour:
        advancement temporal forecast "user_login" --horizon 3600
      
      Forecast errors for next 24 hours:
        advancement temporal forecast "error" --horizon 86400
      
      Forecast with higher confidence (require 10 data points):
        advancement temporal forecast "api_request" --min-points 10
    """
    engine = get_engine()
    try:
        result = engine.forecast(event_type, horizon, min_points)
        
        if "error" in result:
            click.echo(format_output(result, format))
            sys.exit(1)
        
        # Add metadata
        result["request"] = {
            "event_type": event_type,
            "horizon_seconds": horizon,
            "min_data_points": min_points
        }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e), "event_type": event_type}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("name")
@click.argument("delay", type=float)
@click.option("--payload", "-p", default="{}", help="JSON-encoded task payload")
@click.option("--description", "-d", default="", help="Task description")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.option("--verbose", "-v", is_flag=True, help="Show full schedule details")
@click.pass_context
def schedule(ctx, name, delay, payload, description, format, verbose):
    """
    Schedule a one-shot task to execute after a delay.
    
    Returns a schedule_id that can be used to cancel the task before execution.
    
    EXAMPLES:
    
      Schedule alert in 5 seconds:
        advancement temporal schedule "send_alert" 5
      
      Schedule with payload:
        advancement temporal schedule "notify_user" 10 --payload '{"user_id":123,"msg":"hello"}'
      
      Schedule with description:
        advancement temporal schedule "backup_database" 3600 --description "Daily backup"
    """
    engine = get_engine()
    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError:
        error = {"error": "Invalid JSON in payload", "input": payload}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)
    
    try:
        # Schedule with no-op callback (CLI doesn't execute in-process)
        schedule_id = engine.schedule_at(name, delay, lambda d: None, parsed_payload)
        
        result = {
            "schedule_id": schedule_id,
            "task": {
                "name": name,
                "delay_seconds": delay,
                "description": description or "(none)",
                "scheduled": True
            }
        }
        
        if verbose:
            result["payload"] = parsed_payload
            result["scheduled_at"] = time.time()
            result["execute_at"] = time.time() + delay
            result["instructions"] = f"Cancel with: advancement temporal cancel {schedule_id}"
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e), "task": name}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: CANCEL
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("schedule_id")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def cancel(ctx, schedule_id, format):
    """
    Cancel a previously scheduled task by its schedule_id.
    
    EXAMPLES:
    
      Cancel a specific task:
        advancement temporal cancel "abc123def456"
      
      Try cancelling non-existent task (graceful):
        advancement temporal cancel "invalid_id"
    """
    engine = get_engine()
    try:
        cancelled = engine.cancel_schedule(schedule_id)
        
        result = {
            "cancelled": cancelled,
            "schedule_id": schedule_id,
            "status": "cancelled" if cancelled else "not_found"
        }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e), "schedule_id": schedule_id}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.argument("event_types", nargs=-1, required=True)
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def depends(ctx, event_types, format):
    """
    Resolve temporal dependencies between event types.
    
    Determines the chronological order event types occurred based on historical data.
    
    EXAMPLES:
    
      Find order of login, purchase, and payment events:
        advancement temporal depends "login" "purchase" "payment_received"
      
      Analyze three-step workflow:
        advancement temporal depends "request_initiated" "processing" "completed"
    """
    engine = get_engine()
    try:
        chain = engine.temporal_dependency_chain(list(event_types))
        
        result = {
            "dependency_chain": chain,
            "analysis": {
                "input_events": list(event_types),
                "count": len(chain),
                "chronological_order": chain
            }
        }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e), "events": list(event_types)}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: SUMMARY & STATE
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.option("--details", "-d", is_flag=True, help="Show detailed breakdown")
@click.pass_context
def summary(ctx, format, details):
    """
    Show temporal engine state summary.
    
    Includes counts of recorded events, scheduled tasks, and engine statistics.
    
    EXAMPLES:
    
      Quick summary:
        advancement temporal summary
      
      Detailed breakdown:
        advancement temporal summary --details
    """
    engine = get_engine()
    try:
        state = engine.summary()

        result = {
            "engine_state": state,
            "timestamp": time.time()
        }
        
        if details:
            # Add additional details
            result["breakdown"] = {
                "total_events": state["total_events_recorded"],
                "active_events": state["active_events"],
                "expired": state["expired_events"],
                "unique_types": state["unique_event_types"],
                "pending_schedules": state["pending_schedules"],
                "expiration_rate": round(
                    state["expired_events"] / max(state["total_events_recorded"], 1) * 100, 1
                )
            }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e)}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: MCP TOOLS EXPORT (For integration with MCP server)
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.option("--format", "-f", type=click.Choice(["json", "yaml"]), default="json")
@click.pass_context
def tools(ctx, format):
    """
    Export MCP tool definitions for the temporal engine.
    
    Use this to integrate temporal tools into an MCP server.
    
    EXAMPLES:
    
      Export as JSON:
        advancement temporal tools
      
      Export as YAML:
        advancement temporal tools --format yaml
      
      Use in Python:
        tools = json.loads($(advancement temporal tools))
    """
    engine = get_engine()
    try:
        tools_defs = engine.get_tool_definitions()
        
        result = {
            "tools": tools_defs,
            "count": len(tools_defs),
            "version": __version__,
            "module": "temporal_engine"
        }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e)}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORAL: EXECUTE (For async task execution)
# ═══════════════════════════════════════════════════════════════════════════════

@temporal.command()
@click.option("--wait", "-w", is_flag=True, help="Wait for all due schedules to execute")
@click.option("--format", "-f", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def execute(ctx, wait, format):
    """
    Execute all due scheduled tasks immediately.
    
    Returns list of executed schedule IDs.
    
    EXAMPLES:
    
      Execute all due tasks:
        advancement temporal execute
      
      Wait for execution (blocking):
        advancement temporal execute --wait
    """
    engine = get_engine()
    try:
        # Run async execute_scheduled
        executed_ids = asyncio.run(engine.execute_scheduled())
        
        result = {
            "executed": {
                "count": len(executed_ids),
                "schedule_ids": executed_ids
            },
            "timestamp": time.time()
        }
        
        click.echo(format_output(result, format))
    except Exception as e:
        error = {"error": str(e)}
        click.echo(format_output(error, format), err=True)
        sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Entry point for console script."""
    try:
        cli(obj={})
    except Exception as e:
        logger.error(f"CLI error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
