"""
Persistent memory store with semantic search, cross-session learning, and
reinforcement scoring. Built on SQLite with embedding vectors.
"""

import json
import sqlite3
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, NamedTuple

from .logging import setup_logging

logger = setup_logging()

# ═══════════════════════════════════════════════════════════════
# EMBEDDING (Lightweight bag-of-words hashing)
# ═══════════════════════════════════════════════════════════════

VOCAB_SIZE = 1024
STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
              "of", "for", "with", "and", "or", "it", "this", "that", "from", "by"}

def _tokenize(text: str) -> List[str]:
    """Tokenize text, filter stop words and short tokens."""
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) >= 2]

def _feature_hash(token: str) -> int:
    """Hash token to 0..VOCAB_SIZE-1."""
    return int(hashlib.md5(token.encode()).hexdigest(), 16) % VOCAB_SIZE

def _compute_embedding(text: str) -> List[float]:
    """Compute lightweight bag-of-words embedding."""
    vec = [0.0] * VOCAB_SIZE
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        idx = _feature_hash(token)
        vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(v*v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x*y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x*x for x in a))
    norm_b = math.sqrt(sum(y*y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# ═══════════════════════════════════════════════════════════════
# MEMORY STORE
# ═══════════════════════════════════════════════════════════════

class MemoryEntry(NamedTuple):
    """Single memory record."""
    id: int
    agent_name: str
    key: str
    value: str
    metadata: dict
    tags: List[str]
    embedding: List[float]
    created_at: str
    updated_at: str

class MemoryStore:
    """Persistent memory with semantic search and cross-session learning."""

    def __init__(self, db_path: str = "./memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                embedding BLOB,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(agent_name, key)
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_agent ON memories(agent_name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON memories(key)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_tags ON memories(tags)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)")
        self.conn.commit()

    def store(self, agent_name: str, key: str, value: str,
              metadata: Optional[Dict[str, Any]] = None,
              tags: Optional[List[str]] = None) -> int:
        """Store or update a memory entry."""
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        tags_json = json.dumps(tags or [])
        embedding = _compute_embedding(f"{key} {value}".strip())

        cursor = self.conn.execute(
            """
            INSERT INTO memories (agent_name, key, value, metadata, tags, embedding, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_name, key) DO UPDATE SET
                value=excluded.value,
                metadata=excluded.metadata,
                tags=excluded.tags,
                embedding=excluded.embedding,
                updated_at=excluded.updated_at
            """,
            (agent_name, key, value, meta_json, tags_json, json.dumps(embedding), now, now)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get(self, agent_name: str, key: str) -> Optional[str]:
        """Retrieve a memory value by exact key."""
        cursor = self.conn.execute(
            "SELECT value FROM memories WHERE agent_name = ? AND key = ?",
            (agent_name, key)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def delete(self, agent_name: str, key: str) -> bool:
        """Delete a memory entry."""
        cursor = self.conn.execute(
            "DELETE FROM memories WHERE agent_name = ? AND key = ?",
            (agent_name, key)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def search(self, query: str, agent_name: Optional[str] = None,
               limit: int = 5, min_score: float = 0.3) -> List[Dict[str, Any]]:
        """Search memories by semantic similarity."""
        query_vec = _compute_embedding(query)
        
        sql = "SELECT id, agent_name, key, value, metadata, tags, embedding, created_at, updated_at FROM memories"
        params = []
        
        if agent_name:
            sql += " WHERE agent_name = ?"
            params.append(agent_name)
        
        cursor = self.conn.execute(sql, params)
        results = []
        
        for row in cursor.fetchall():
            id_, agent, key, value, meta_json, tags_json, emb_json, created, updated = row
            emb = json.loads(emb_json) if emb_json else [0.0] * VOCAB_SIZE
            score = cosine_similarity(query_vec, emb)
            
            if score >= min_score:
                results.append({
                    "id": id_,
                    "agent_name": agent,
                    "key": key,
                    "value": value,
                    "metadata": json.loads(meta_json),
                    "tags": json.loads(tags_json),
                    "score": round(score, 4),
                    "created_at": created,
                    "updated_at": updated,
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def list_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """List all memories for an agent."""
        cursor = self.conn.execute(
            "SELECT id, key, value, metadata FROM memories WHERE agent_name = ? ORDER BY updated_at DESC",
            (agent_name,)
        )
        return [
            {"id": r[0], "key": r[1], "value": r[2], "metadata": json.loads(r[3])}
            for r in cursor.fetchall()
        ]

    def compact(self) -> dict:
        """Remove duplicate/stale entries and vacuum database."""
        # Remove duplicates, keeping newest
        self.conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT MAX(id) FROM memories GROUP BY agent_name, key
            )
        """)
        self.conn.execute("VACUUM")
        self.conn.commit()
        return {"status": "compacted", "timestamp": datetime.now(timezone.utc).isoformat()}

    def close(self):
        """Close database connection."""
        self.conn.close()
