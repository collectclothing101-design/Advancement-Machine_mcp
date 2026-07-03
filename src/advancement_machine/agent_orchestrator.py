"""
Agent Orchestrator — routes intents to specialized agents, manages memory,
and coordinates multi-agent workflows with hooks and event handlers.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime, timezone

from .memory import MemoryStore
from .plugin_loader import PluginManager
from .logging import setup_logging

logger = setup_logging()

class AgentRoute:
    """Metadata for an agent route."""
    def __init__(self, agent_name: str, description: str, keywords: List[str],
                 fn: Optional[Callable] = None):
        self.agent_name = agent_name
        self.description = description
        self.keywords = keywords
        self.fn = fn

class AgentOrchestrator:
    """
    Routes intents through specialized agents, manages memory across agents,
    and handles multi-agent coordination with hooks and memory reinforcement.
    """

    def __init__(self, plugin_manager: Optional[PluginManager] = None,
                 memory_db: str = "./memory.db"):
        self.plugin_manager = plugin_manager
        self.memory = MemoryStore(memory_db)
        self._agents: Dict[str, AgentRoute] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        self._discover_agents()

    def _discover_agents(self):
        """Discover agents from plugins."""
        if not self.plugin_manager:
            return
        
        for plugin in self.plugin_manager.all():
            for hook in plugin.get_hooks("agent_route"):
                if hasattr(hook, "route_def"):
                    route = hook.route_def
                    self._agents[route.agent_name] = route
                    logger.info(f"Registered agent: {route.agent_name}")

    def register_agent(self, agent_name: str, description: str,
                      keywords: List[str],
                      fn: Optional[Callable[[str, Dict], Awaitable[Any]]] = None):
        """Manually register an agent."""
        route = AgentRoute(agent_name, description, keywords, fn)
        self._agents[agent_name] = route

    async def route(self, intent: str) -> Optional[AgentRoute]:
        """Find the best-matching agent for an intent."""
        intent_lower = intent.lower()
        
        # Exact keyword match first
        for agent_name, route in self._agents.items():
            for keyword in route.keywords:
                if keyword.lower() in intent_lower:
                    return route
        
        # Partial match
        for agent_name, route in self._agents.items():
            for keyword in route.keywords:
                if keyword.lower() in intent_lower or intent_lower in keyword.lower():
                    return route
        
        return None

    async def handle_intent(self, intent: str, context: Optional[Dict] = None) -> Any:
        """Route an intent and execute the matched agent."""
        context = context or {}
        context["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        route = await self.route(intent)
        if not route:
            return {"error": f"No agent matched intent: {intent}"}
        
        try:
            if route.fn:
                result = await route.fn(intent, context)
            else:
                result = {"agent": route.agent_name, "intent": intent, "status": "no_handler"}
            
            # Store in memory
            await self.store_memory(
                agent_name=route.agent_name,
                key=f"intent:{intent[:50]}",
                value=json.dumps(result),
                tags=["intent", "handled"]
            )
            
            return result
        except Exception as e:
            logger.error(f"Agent {route.agent_name} failed: {e}", exc_info=True)
            return {"error": str(e), "agent": route.agent_name}

    async def store_memory(self, agent_name: str, key: str, value: str,
                          metadata: Optional[Dict] = None,
                          tags: Optional[List[str]] = None) -> int:
        """Store memory and trigger on_store hooks."""
        # Trigger hooks
        for hook in self._hooks.get("on_store", []):
            try:
                await hook(agent_name=agent_name, key=key, value=value)
            except Exception as e:
                logger.warning(f"on_store hook failed: {e}")
        
        # Store
        mem_id = self.memory.store(agent_name, key, value, metadata, tags)
        logger.debug(f"Stored memory {mem_id} for {agent_name}:{key}")
        return mem_id

    async def search_memory(self, query: str, agent_name: Optional[str] = None,
                           limit: int = 5) -> List[Dict]:
        """Search memory by semantic similarity."""
        result = self.memory.search(query, agent_name=agent_name, limit=limit)
        
        # Trigger hooks
        for hook in self._hooks.get("on_search", []):
            try:
                await hook(query=query, results=result)
            except Exception as e:
                logger.warning(f"on_search hook failed: {e}")
        
        return result

    async def forget_memory(self, agent_name: str, key: str) -> bool:
        """Delete a memory entry and trigger on_forget hooks."""
        # Trigger hooks
        for hook in self._hooks.get("on_forget", []):
            try:
                await hook(agent_name=agent_name, key=key)
            except Exception as e:
                logger.warning(f"on_forget hook failed: {e}")
        
        # Delete
        deleted = self.memory.delete(agent_name, key)
        if deleted:
            logger.debug(f"Forgot memory {agent_name}:{key}")
        return deleted

    async def undo_forget(self, agent_name: str, key: str) -> bool:
        """Attempt to restore a forgotten memory (placeholder for future implementation)."""
        # This would require audit log tracking of deleted memories
        # For now, return False
        return False

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents."""
        return [
            {
                "name": route.agent_name,
                "description": route.description,
                "keywords": route.keywords,
            }
            for route in self._agents.values()
        ]

    def register_hook(self, hook_name: str, fn: Callable):
        """Register a hook for events like on_store, on_search, on_forget."""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(fn)

    async def compact_memory(self) -> dict:
        """Compact and optimize memory database."""
        result = self.memory.compact()
        logger.info("Memory compacted")
        return result

    def close(self):
        """Close connections."""
        self.memory.close()
