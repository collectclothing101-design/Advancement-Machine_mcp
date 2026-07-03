from typing import Any, Callable, Coroutine, Optional, Dict, List
from pydantic import BaseModel, Field, ValidationError

class ToolDef(BaseModel):
    name: str
    description: str
    input_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

class AgentRoute(BaseModel):
    agent_name: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    fn: Optional[Callable[[str, dict], Coroutine[Any, Any, Any]]] = None

class StoreModification(BaseModel):
    modified_value: Optional[str] = None
    modified_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

def validate_store_modification(data: dict) -> dict:
    try:
        validated = StoreModification(**data)
        result = {}
        if validated.modified_value is not None:
            result["modified_value"] = validated.modified_value
        if validated.modified_metadata is not None:
            result["modified_metadata"] = validated.modified_metadata
        if validated.tags is not None:
            result["tags"] = validated.tags
        return result
    except ValidationError as e:
        logger = __import__('logging').getLogger(__name__)
        logger.error(f"on_store hook returned invalid schema: {e}")
        return {}

def mcp_tool(name: str, description: str, input_schema: dict = None):
    def decorator(func: Callable):
        func._plugin_hook = "mcp_tool"
        func.tool_def = ToolDef(name=name, description=description,
                                 input_schema=input_schema or {"type": "object", "properties": {}, "required": []})
        return func
    return decorator

def mcp_resource(uri: str, name: str, description: str):
    def decorator(func: Callable):
        func._plugin_hook = "mcp_resource"
        func.resource_def = {"uri": uri, "name": name, "description": description}
        return func
    return decorator

def agent_route(agent_name: str, description: str, keywords: list[str] = None):
    def decorator(func: Callable):
        func._plugin_hook = "agent_route"
        func.route_def = AgentRoute(agent_name=agent_name, description=description,
                                     keywords=keywords or [agent_name.lower()], fn=func)
        return func
    return decorator

def skill_action(name: str, description: str):
    def decorator(func: Callable):
        func._plugin_hook = "skill_action"
        func.action_def = {"name": name, "description": description}
        return func
    return decorator

def on_store(func: Callable = None, *, priority: int = 100):
    def wrapper(f):
        f._plugin_hook = "on_store"
        f._hook_priority = priority
        f._hook_schema_validator = validate_store_modification
        return f
    if func is not None:
        return wrapper(func)
    return wrapper

def on_search(func: Callable = None, *, priority: int = 100):
    def wrapper(f):
        f._plugin_hook = "on_search"
        f._hook_priority = priority
        return f
    if func is not None:
        return wrapper(func)
    return wrapper

def on_forget(func: Callable = None, *, priority: int = 100):
    def wrapper(f):
        f._plugin_hook = "on_forget"
        f._hook_priority = priority
        return f
    if func is not None:
        return wrapper(func)
    return wrapper