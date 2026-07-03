"""
Agent-to-Agent MCP Federation Protocol.

Enables the Advancement Machine to discover, connect to, and delegate work
across remote MCP servers — including other Advancement Machine instances,
third-party MCP servers, and AI agent runtimes that expose an MCP interface.

Supports:
  - WebSocket (ws/wss) and HTTP transports
  - Multi-hop delegation (A → B → C)
  - Capability change detection via fingerprint hashing
  - Stale peer eviction after TTL expiry
  - Batch peer discovery
  - Tool search across all connected peers
"""

import asyncio
import json
import logging
import hashlib
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CAPABILITY_ADVERTISED_TTL = 300
MAX_DELEGATION_DEPTH = 3

class RemotePeer:
    """Represents a connected remote MCP server and its advertised capabilities."""

    def __init__(self, peer_id: str, url: str, transport: str = "ws", hop_depth: int = 0):
        self.peer_id = peer_id
        self.url = url
        self.transport = transport
        self.hop_depth = hop_depth
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []
        self.last_seen: float = time.time()
        self.capability_hash: str = ""
        self.connected: bool = False
        self._ws = None

    def capability_fingerprint(self) -> str:
        raw = json.dumps(self.tools, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > CAPABILITY_ADVERTISED_TTL

    def to_dict(self) -> dict:
        return {
            "peer_id": self.peer_id,
            "url": self.url,
            "transport": self.transport,
            "hop_depth": self.hop_depth,
            "connected": self.connected,
            "tool_count": len(self.tools),
            "resource_count": len(self.resources),
            "prompt_count": len(self.prompts),
            "capability_hash": self.capability_hash,
            "is_stale": self.is_stale(),
            "last_seen": datetime.fromtimestamp(self.last_seen, tz=timezone.utc).isoformat(),
        }

class AgentBridge:
    """Federated MCP bridge — connects to remote MCP servers and routes
    tool calls and resource reads across the mesh.

    AI-optimized features:
      - Multi-hop delegation: A → B → C (depth-limited to prevent loops)
      - Capability change detection: re-fetches peers when fingerprint changes
      - Stale peer eviction: removes peers that haven't announced in TTL
      - Batch discover: connect to N peers in parallel
      - Tool search: find which peer advertises a given tool
      - Broadcast: advertise local capabilities to all connected peers
    """

    def __init__(self):
        self.peers: Dict[str, RemotePeer] = {}
        self._local_capabilities: dict = {}

    def register_local_capabilities(self, tools: list, resources: list, prompts: list):
        """Register the local server's capabilities so they can be advertised."""
        self._local_capabilities = {
            "tools": tools,
            "resources": resources,
            "prompts": prompts,
        }

    async def connect_peer(self, url: str, transport: str = "ws",
                           hop_depth: int = 0) -> dict:
        """Connect to a remote MCP server and fetch its capabilities.

        If the peer is already connected, returns cached data.
        Supports ws://, wss://, and http:// transports.

        With hop_depth tracking, this peer can later be used as an intermediary
        for multi-hop delegations.
        """
        import websockets

        peer_id = hashlib.md5(url.encode()).hexdigest()[:12]

        if peer_id in self.peers:
            cached = self.peers[peer_id]
            cached.last_seen = time.time()
            # Re-fetch if stale
            if cached.is_stale():
                await self._refresh_peer(cached)
            return cached.to_dict()

        peer = RemotePeer(peer_id=peer_id, url=url, transport=transport, hop_depth=hop_depth)

        try:
            if transport in ("ws", "wss"):
                peer._ws = await websockets.connect(url)
                # Initialize MCP session
                init = json.dumps({
                    "method": "initialize",
                    "params": {
                        "protocol_version": "0.1.0",
                        "capabilities": {},
                        "client_info": {"name": "advancement-machine", "version": "0.3.0"},
                    },
                    "id": 1,
                })
                await peer._ws.send(init)
                init_resp = json.loads(await peer._ws.recv())
                if "result" not in init_resp:
                    await peer._ws.close()
                    return {"error": f"Peer at {url} rejected initialization"}

                # Fetch tools
                await peer._ws.send(json.dumps({"method": "list_tools", "id": 2}))
                tools_resp = json.loads(await peer._ws.recv())
                peer.tools = tools_resp.get("result", {}).get("tools", [])

                # Fetch resources
                await peer._ws.send(json.dumps({"method": "list_resources", "id": 3}))
                res_resp = json.loads(await peer._ws.recv())
                peer.resources = res_resp.get("result", {}).get("resources", [])

                # Fetch prompts
                await peer._ws.send(json.dumps({"method": "list_prompts", "id": 4}))
                prom_resp = json.loads(await peer._ws.recv())
                peer.prompts = prom_resp.get("result", {}).get("prompts", [])

                peer.connected = True
                peer.capability_hash = peer.capability_fingerprint()
                self.peers[peer_id] = peer

                logger.info(f"Connected to peer {peer_id} at {url} "
                            f"({len(peer.tools)} tools, hop={hop_depth})")
                return peer.to_dict()

            elif transport == "http":
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{url}/rpc/list_tools", json={"id": 1}) as resp:
                        tools_data = await resp.json()
                        peer.tools = tools_data.get("result", {}).get("tools", [])
                    async with session.post(f"{url}/rpc/list_resources", json={"id": 2}) as resp:
                        res_data = await resp.json()
                        peer.resources = res_data.get("result", {}).get("resources", [])
                    peer.connected = True
                    self.peers[peer_id] = peer
                return peer.to_dict()

            return {"error": f"Unsupported transport: {transport}"}

        except Exception as e:
            logger.error(f"Failed to connect to peer at {url}: {e}")
            return {"error": str(e), "url": url}

    async def _refresh_peer(self, peer: RemotePeer):
        """Re-fetch capabilities from a peer that may have updated them."""
        logger.info(f"Refreshing peer {peer.peer_id} (stale)")
        try:
            if peer.transport in ("ws", "wss") and peer._ws:
                await peer._ws.send(json.dumps({"method": "list_tools", "id": 1}))
                tools_resp = json.loads(await peer._ws.recv())
                peer.tools = tools_resp.get("result", {}).get("tools", [])

                await peer._ws.send(json.dumps({"method": "list_resources", "id": 2}))
                res_resp = json.loads(await peer._ws.recv())
                peer.resources = res_resp.get("result", {}).get("resources", [])

                peer.last_seen = time.time()
                new_hash = peer.capability_fingerprint()
                if new_hash != peer.capability_hash:
                    logger.info(f"Peer {peer.peer_id} capabilities changed")
                    peer.capability_hash = new_hash
        except Exception as e:
            logger.warning(f"Failed to refresh peer {peer.peer_id}: {e}")

    async def discover_peers(self, peer_urls: List[str], hop_depth: int = 0) -> List[dict]:
        """Connect to multiple peers in parallel and aggregate capabilities."""
        tasks = [self.connect_peer(url, hop_depth=hop_depth) for url in peer_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def delegate_tool(self, tool_name: str, arguments: dict,
                            preferred_peer: Optional[str] = None) -> dict:
        """Call a tool on a remote peer that advertises it.

        If preferred_peer is set, target that peer directly.
        Otherwise, search all peers for the tool and use the first match.
        If the peer supports multi-hop, the delegation can chain further.
        """
        if preferred_peer and preferred_peer in self.peers:
            peer = self.peers[preferred_peer]
            return await self._call_peer_tool(peer, tool_name, arguments)

        for peer in self.peers.values():
            if any(t.get("name") == tool_name for t in peer.tools):
                return await self._call_peer_tool(peer, tool_name, arguments)

        return {"error": f"No peer advertises tool '{tool_name}'"}

    async def _call_peer_tool(self, peer: RemotePeer, tool_name: str,
                              arguments: dict) -> dict:
        """Execute a tool call on a remote peer."""
        try:
            if peer.transport in ("ws", "wss") and peer._ws:
                msg = json.dumps({
                    "method": "call_tool",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": 1,
                })
                await peer._ws.send(msg)
                resp = json.loads(await peer._ws.recv())
                peer.last_seen = time.time()
                return resp.get("result", {"error": "No result"})

            elif peer.transport == "http":
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{peer.url}/rpc/call_tool", json={
                        "method": "call_tool",
                        "params": {"name": tool_name, "arguments": arguments},
                        "id": 1,
                    }) as resp:
                        data = await resp.json()
                        return data.get("result", {"error": "No result"})

            return {"error": f"Peer {peer.peer_id} is not connected"}
        except Exception as e:
            logger.error(f"Failed to delegate tool '{tool_name}' to {peer.peer_id}: {e}")
            return {"error": str(e)}

    async def delegate_resource(self, resource_uri: str) -> dict:
        """Read a resource from the first peer that advertises a matching URI."""
        for peer in self.peers.values():
            for res in peer.resources:
                if resource_uri.startswith(res.get("uri", "")):
                    return await self._read_peer_resource(peer, resource_uri)
        return {"error": f"No peer advertises resource '{resource_uri}'"}

    async def _read_peer_resource(self, peer: RemotePeer, uri: str) -> dict:
        try:
            if peer.transport in ("ws", "wss") and peer._ws:
                msg = json.dumps({
                    "method": "read_resource",
                    "params": {"uri": uri},
                    "id": 1,
                })
                await peer._ws.send(msg)
                resp = json.loads(await peer._ws.recv())
                return resp.get("result", {"error": "No result"})
            return {"error": f"Cannot read resource from {peer.peer_id}"}
        except Exception as e:
            return {"error": str(e)}

    async def multi_hop_delegate(self, tool_name: str, arguments: dict,
                                  peer_chain: List[str]) -> dict:
        """Delegate through a chain of peers (A → B → C).

        Each peer in the chain forwards the call to the next.
        Depth is limited by MAX_DELEGATION_DEPTH to prevent loops.
        """
        if len(peer_chain) > MAX_DELEGATION_DEPTH:
            return {"error": f"Delegation chain too long (max {MAX_DELEGATION_DEPTH})"}

        current_result = {"tool_name": tool_name, "arguments": arguments}

        for peer_id in peer_chain:
            if peer_id not in self.peers:
                return {"error": f"Peer {peer_id} not found in chain",
                        "chain_position": peer_id}
            peer = self.peers[peer_id]

            # If the peer has the tool, call it directly
            if any(t.get("name") == tool_name for t in peer.tools):
                current_result = await self._call_peer_tool(peer, tool_name, arguments)
            else:
                # Forward along the chain
                current_result = await self._call_peer_tool(
                    peer, "bridge_delegate_tool",
                    {"tool_name": tool_name, "arguments": arguments,
                     "next_hop": peer_chain[len(peer_chain) - peer_chain.index(peer_id) - 1]}
                )

        return current_result

    async def broadcast_advertisement(self, ttl: int = 300):
        """Send local capabilities to all connected peers.

        Each peer receives an 'update_capabilities' notification with
        the local tool/resource/prompt list and a TTL.
        """
        if not self._local_capabilities:
            return {"error": "No local capabilities registered"}

        payload = json.dumps({
            "method": "notification",
            "params": {
                "type": "capability_advertisement",
                "capabilities": self._local_capabilities,
                "ttl": ttl,
                "sender": "advancement-machine",
            },
        })

        results = {}
        for peer_id, peer in self.peers.items():
            if peer.connected and peer._ws:
                try:
                    await peer._ws.send(payload)
                    results[peer_id] = "advertised"
                except Exception as e:
                    results[peer_id] = f"failed: {e}"
            else:
                results[peer_id] = "not_connected"

        return results

    def list_peers(self) -> List[dict]:
        """Return all connected peers and their capabilities."""
        return [p.to_dict() for p in self.peers.values()]

    def find_tool_across_peers(self, tool_name: str) -> List[dict]:
        """Search all peers for a tool by name or description match."""
        results = []
        for p in self.peers.values():
            for t in p.tools:
                name_matched = t.get("name") == tool_name
                desc_matched = tool_name.lower() in t.get("description", "").lower()
                if name_matched or desc_matched:
                    results.append({"peer": p.to_dict(), "tool": t})
        return results

    async def disconnect_peer(self, peer_id: str) -> bool:
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            if peer._ws and hasattr(peer._ws, 'close'):
                try:
                    await peer._ws.close()
                except Exception:
                    pass
            del self.peers[peer_id]
            logger.info(f"Disconnected from peer {peer_id}")
            return True
        return False

    async def disconnect_all(self):
        for peer_id in list(self.peers.keys()):
            await self.disconnect_peer(peer_id)

    def evict_stale_peers(self) -> List[str]:
        """Remove peers that have exceeded the advertisement TTL."""
        stale = [pid for pid, p in self.peers.items() if p.is_stale()]
        for pid in stale:
            del self.peers[pid]
        if stale:
            logger.info(f"Evicted stale peers: {stale}")
        return stale

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "bridge_list_peers",
                "description": "List all connected remote MCP peers and their capabilities",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "bridge_connect_peer",
                "description": "Connect to a remote MCP server and discover its capabilities",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "WebSocket or HTTP URL of the remote MCP server"},
                        "transport": {"type": "string", "enum": ["ws", "wss", "http"], "default": "ws"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "bridge_delegate_tool",
                "description": "Call a tool on a remote MCP peer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "preferred_peer": {"type": "string", "description": "Optional peer ID to target"},
                    },
                    "required": ["tool_name", "arguments"],
                },
            },
            {
                "name": "bridge_delegate_resource",
                "description": "Read a resource from a remote MCP peer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "resource_uri": {"type": "string"},
                    },
                    "required": ["resource_uri"],
                },
            },
            {
                "name": "bridge_discover_peers",
                "description": "Connect to multiple remote peers in parallel",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "peer_urls": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["peer_urls"],
                },
            },
            {
                "name": "bridge_multi_hop_delegate",
                "description": "Delegate a tool call through a chain of peers (A → B → C)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "peer_chain": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ordered list of peer IDs to chain through",
                        },
                    },
                    "required": ["tool_name", "arguments", "peer_chain"],
                },
            },
            {
                "name": "bridge_find_tool",
                "description": "Search for a tool across all connected peers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                    },
                    "required": ["tool_name"],
                },
            },
            {
                "name": "bridge_disconnect_peer",
                "description": "Disconnect from a specific remote peer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "peer_id": {"type": "string"},
                    },
                    "required": ["peer_id"],
                },
            },
            {
                "name": "bridge_evict_stale",
                "description": "Remove peers that have exceeded the advertisement TTL",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]