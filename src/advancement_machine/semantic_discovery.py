"""
Semantic Discovery — embedding-based tool search and vector similarity matching.

Every tool, resource, and prompt in the MCP server is indexed by its semantic
embedding. AI agents can search by natural language intent rather than exact
names, and the engine returns the top-N best-matching capabilities.

The embedding pipeline uses the same lightweight bag-of-words hashing as the
memory module. For production, swap in sentence-transformers by overriding
the `compute_embedding` import.
"""

import hashlib
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .mcp_server import TemporalMCPServer as AdvancementMCPServer

logger = logging.getLogger(__name__)

VOCAB_SIZE = 1024
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
              "of", "for", "with", "and", "or", "it", "this", "that", "from", "by"}

def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) >= 2]

def _feature_hash(token: str) -> int:
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % VOCAB_SIZE

def _compute_embedding(text: str) -> List[float]:
    vec = [0.0] * VOCAB_SIZE
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        idx = _feature_hash(token)
        vec[idx] += 1.0
    norm = math.sqrt(sum(v*v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec

def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x*x for x in a))
    norm_b = math.sqrt(sum(y*y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

class SemanticIndex:
    """Indexes every tool, resource, and prompt by its semantic embedding.

    AI agents or users can query the index with natural language to discover
    capabilities without knowing exact tool names.
    """

    def __init__(self, mcp_server: Optional[AdvancementMCPServer] = None):
        self.mcp_server = mcp_server
        self._tool_index: List[dict] = []
        self._resource_index: List[dict] = []
        self._prompt_index: List[dict] = []
        self._built = False

    def set_server(self, mcp_server: AdvancementMCPServer):
        self.mcp_server = mcp_server
        self._built = False

    def build_index(self) -> dict:
        """Scan the MCP server and build the semantic index."""
        self._tool_index = []
        self._resource_index = []
        self._prompt_index = []

        if not self.mcp_server or not hasattr(self.mcp_server, 'server'):
            logger.warning("No MCP server set — index will be empty")
            self._built = True
            return {"status": "empty", "reason": "No MCP server"}

        server = self.mcp_server.server

        # Index tools
        if hasattr(server, 'tools'):
            for tool in server.tools:
                text = f"{tool.name} {tool.description}"
                embedding = _compute_embedding(text)
                self._tool_index.append({
                    "name": tool.name,
                    "description": tool.description,
                    "type": "tool",
                    "input_schema": tool.inputSchema,
                    "embedding": embedding,
                })

        # Index resources
        if hasattr(server, 'resources'):
            for res in server.resources:
                text = f"{res.uri} {res.name} {res.description}"
                embedding = _compute_embedding(text)
                self._resource_index.append({
                    "uri": res.uri,
                    "name": res.name,
                    "description": res.description,
                    "type": "resource",
                    "mime_type": res.mimeType,
                    "embedding": embedding,
                })

        # Index prompts
        if hasattr(server, 'prompts'):
            for prompt in server.prompts:
                text = f"{prompt.name} {prompt.description}"
                arg_text = " ".join(a.get("name", "") for a in (prompt.arguments or []))
                full_text = f"{text} {arg_text}"
                embedding = _compute_embedding(full_text)
                self._prompt_index.append({
                    "name": prompt.name,
                    "description": prompt.description,
                    "type": "prompt",
                    "arguments": prompt.arguments,
                    "embedding": embedding,
                })

        self._built = True
        return {
            "status": "built",
            "tools": len(self._tool_index),
            "resources": len(self._resource_index),
            "prompts": len(self._prompt_index),
            "total": len(self._tool_index) + len(self._resource_index) + len(self._prompt_index),
        }

    def search_tools(self, query: str, top_k: int = 5,
                     min_score: float = 0.2) -> List[dict]:
        """Search indexed tools by semantic similarity to a natural language query.

        Returns the top-K tools ranked by cosine similarity score.
        """
        if not self._built:
            self.build_index()

        query_vec = _compute_embedding(query)
        scored = []
        for entry in self._tool_index:
            score = cosine_similarity(query_vec, entry["embedding"])
            if score >= min_score:
                scored.append({
                    "name": entry["name"],
                    "description": entry["description"],
                    "type": "tool",
                    "score": round(score, 4),
                    "input_schema": entry.get("input_schema"),
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_resources(self, query: str, top_k: int = 5,
                         min_score: float = 0.2) -> List[dict]:
        """Search indexed resources by semantic similarity."""
        if not self._built:
            self.build_index()

        query_vec = _compute_embedding(query)
        scored = []
        for entry in self._resource_index:
            score = cosine_similarity(query_vec, entry["embedding"])
            if score >= min_score:
                scored.append({
                    "uri": entry["uri"],
                    "name": entry["name"],
                    "description": entry["description"],
                    "type": "resource",
                    "score": round(score, 4),
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_prompts(self, query: str, top_k: int = 5,
                       min_score: float = 0.2) -> List[dict]:
        """Search indexed prompts by semantic similarity."""
        if not self._built:
            self.build_index()

        query_vec = _compute_embedding(query)
        scored = []
        for entry in self._prompt_index:
            score = cosine_similarity(query_vec, entry["embedding"])
            if score >= min_score:
                scored.append({
                    "name": entry["name"],
                    "description": entry["description"],
                    "type": "prompt",
                    "score": round(score, 4),
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_all(self, query: str, top_k: int = 5,
                   min_score: float = 0.2) -> dict:
        """Search all indexed capabilities at once.

        Returns a merged result set with tools, resources, and prompts
        ranked together by similarity score.
        """
        if not self._built:
            self.build_index()

        all_entries = []
        for entry in self._tool_index:
            all_entries.append(entry)
            all_entries[-1]["category"] = "tool"
        for entry in self._resource_index:
            all_entries.append(entry)
            all_entries[-1]["category"] = "resource"
        for entry in self._prompt_index:
            all_entries.append(entry)
            all_entries[-1]["category"] = "prompt"

        query_vec = _compute_embedding(query)
        scored = []
        for entry in all_entries:
            score = cosine_similarity(query_vec, entry["embedding"])
            if score >= min_score:
                result_entry = {
                    "name": entry.get("name") or entry.get("uri", ""),
                    "description": entry.get("description", ""),
                    "category": entry["category"],
                    "score": round(score, 4),
                }
                if "uri" in entry:
                    result_entry["uri"] = entry["uri"]
                scored.append(result_entry)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return {
            "query": query,
            "results": scored[:top_k],
            "total_matches": len(scored),
        }

    def summary(self) -> dict:
        """Return a summary of the index for AI consumption."""
        if not self._built:
            self.build_index()
        return {
            "indexed": self._built,
            "tools": len(self._tool_index),
            "resources": len(self._resource_index),
            "prompts": len(self._prompt_index),
            "total_entries": len(self._tool_index) + len(self._resource_index) + len(self._prompt_index),
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "semantic_search_tools",
                "description": "Search MCP tools by natural language intent — uses vector similarity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_search_resources",
                "description": "Search MCP resources by natural language intent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_search_prompts",
                "description": "Search MCP prompts by natural language intent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_search_all",
                "description": "Search all MCP capabilities (tools, resources, prompts) by semantic similarity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_index_status",
                "description": "Get the status of the semantic search index",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]