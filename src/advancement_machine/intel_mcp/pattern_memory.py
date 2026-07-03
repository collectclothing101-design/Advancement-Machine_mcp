"""
Pattern Memory: SQLite-based pattern storage with query frequency scoring and deduplication.

Features:
  - Hash-based pattern matching (SHA256, first 16 chars)
  - Query frequency scoring (prevent duplicate suggestions)
  - Best-pick deduplication algorithm
  - Pattern relationships and metadata
  - Reuse counting (track pattern adoption)
  - Timestamped updates (first_seen, last_seen)
"""

import sqlite3
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPattern:
    """Base pattern structure."""
    type: str
    title: str
    content: str
    confidence: float = 0.5
    reusability: float = 0.5
    tags: Optional[List[str]] = None
    source_file: str = ""


@dataclass
class StoredPattern(ExtractedPattern):
    """Pattern stored in database with metadata."""
    id: int = 0
    hash: str = ""
    source_repo: str = ""
    reuse_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    query_frequency: int = 0  # NEW: Commit 31e6cff feature


class PatternMemory:
    """
    SQLite-based pattern storage with query frequency scoring.
    
    Implements:
      - Pattern deduplication (hash-based)
      - Query frequency scoring (counter-based)
      - Best-pick selection (top-N unique by frequency)
      - Reuse counting (adoption tracking)
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize pattern memory with SQLite backend."""
        if db_path is None:
            db_path = str(Path.home() / ".advancement_machine_intel" / "patterns.db")
        
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = self._init_db()
        logger.debug(f"PatternMemory initialized at {db_path}")
    
    def _init_db(self) -> sqlite3.Connection:
        """Initialize SQLite database with schema."""
        db = sqlite3.connect(self.db_path)
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA foreign_keys = ON")
        
        # Main patterns table
        db.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                source_repo TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                reusability REAL NOT NULL DEFAULT 0.5,
                title TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                reuse_count INTEGER NOT NULL DEFAULT 0,
                query_frequency INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)
        
        # Pattern relationships (for deduplication tracking)
        db.execute("""
            CREATE TABLE IF NOT EXISTS pattern_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id INTEGER NOT NULL,
                similar_pattern_id INTEGER NOT NULL,
                similarity_score REAL NOT NULL,
                FOREIGN KEY (pattern_id) REFERENCES patterns(id),
                FOREIGN KEY (similar_pattern_id) REFERENCES patterns(id),
                UNIQUE(pattern_id, similar_pattern_id)
            )
        """)
        
        # Processed repos (avoid re-processing)
        db.execute("""
            CREATE TABLE IF NOT EXISTS processed_repos (
                full_name TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
        """)
        
        # Query frequency log (for scoring)
        db.execute("""
            CREATE TABLE IF NOT EXISTS query_frequency_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id INTEGER NOT NULL,
                query_context TEXT NOT NULL,
                queried_at TEXT NOT NULL,
                FOREIGN KEY (pattern_id) REFERENCES patterns(id)
            )
        """)
        
        # Create indices
        db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_hash ON patterns(hash)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(type)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_source ON patterns(source_repo)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_reuse ON patterns(reuse_count)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_frequency ON patterns(query_frequency)")
        
        db.commit()
        return db
    
    @staticmethod
    def _hash_pattern(pattern: ExtractedPattern) -> str:
        """Generate SHA256 hash for pattern deduplication."""
        key = f"{pattern.type}::{pattern.title}::{pattern.content[:500]}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def store_pattern(self, pattern: ExtractedPattern, source_repo: str) -> StoredPattern:
        """
        Store pattern with deduplication.
        
        If pattern already exists (by hash):
          - Increment reuse_count
          - Update last_seen
          - Return existing pattern
        
        Otherwise:
          - Insert new pattern
          - Initialize query_frequency = 1
        """
        pattern_hash = self._hash_pattern(pattern)
        now = datetime.now(timezone.utc).isoformat() + "Z"
        tags_json = json.dumps(pattern.tags or [])
        
        # Check for existing pattern
        cursor = self.db.execute(
            "SELECT * FROM patterns WHERE hash = ?",
            (pattern_hash,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing: bump reuse count, update last_seen
            self.db.execute(
                """UPDATE patterns 
                   SET last_seen = ?, reuse_count = reuse_count + 1, query_frequency = query_frequency + 1
                   WHERE hash = ?""",
                (now, pattern_hash)
            )
            self.db.commit()
            return self._row_to_stored_pattern(
                self.db.execute("SELECT * FROM patterns WHERE hash = ?", (pattern_hash,)).fetchone()
            )
        
        # Insert new pattern
        cursor = self.db.execute("""
            INSERT INTO patterns (hash, type, source_repo, content, confidence, reusability, title, tags, reuse_count, query_frequency, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
        """, (
            pattern_hash,
            pattern.type,
            source_repo,
            pattern.content,
            pattern.confidence,
            pattern.reusability,
            pattern.title,
            tags_json,
            now,
            now
        ))
        self.db.commit()
        
        row = self.db.execute(
            "SELECT * FROM patterns WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()
        
        return self._row_to_stored_pattern(row)
    
    def find_similar(self, pattern: ExtractedPattern, limit: int = 5) -> List[StoredPattern]:
        """
        Find similar patterns by type.
        
        Strategy:
          1. Check for exact hash match first
          2. Fall back to type-based similarity
          3. Return top-N by query_frequency (best-pick dedup)
        """
        pattern_hash = self._hash_pattern(pattern)
        
        # Exact match
        cursor = self.db.execute(
            "SELECT * FROM patterns WHERE hash = ?",
            (pattern_hash,)
        )
        exact = cursor.fetchone()
        if exact:
            return [self._row_to_stored_pattern(exact)]
        
        # Type-based similarity (sorted by query frequency for best-pick)
        cursor = self.db.execute(
            """SELECT * FROM patterns 
               WHERE type = ?
               ORDER BY query_frequency DESC, reuse_count DESC
               LIMIT ?""",
            (pattern.type, limit)
        )
        
        return [self._row_to_stored_pattern(row) for row in cursor.fetchall()]
    
    def get_best_picks(self, pattern_type: str, limit: int = 3) -> List[StoredPattern]:
        """
        Get best-pick patterns by query frequency and reuse count.
        
        Used for deduplication: selects top-N most-queried and most-reused patterns.
        """
        cursor = self.db.execute("""
            SELECT * FROM patterns
            WHERE type = ?
            ORDER BY query_frequency DESC, reuse_count DESC
            LIMIT ?
        """, (pattern_type, limit))
        
        return [self._row_to_stored_pattern(row) for row in cursor.fetchall()]
    
    def increment_query_frequency(self, pattern_id: int, context: str = "") -> None:
        """Increment query frequency counter for pattern scoring."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        self.db.execute("""
            INSERT INTO query_frequency_log (pattern_id, query_context, queried_at)
            VALUES (?, ?, ?)
        """, (pattern_id, context, now))
        
        self.db.execute(
            "UPDATE patterns SET query_frequency = query_frequency + 1 WHERE id = ?",
            (pattern_id,)
        )
        self.db.commit()
    
    def get_query_frequency_score(self, pattern_id: int) -> float:
        """
        Get query frequency score (0-1).
        
        Score = query_frequency / max_frequency (normalized)
        """
        cursor = self.db.execute("SELECT query_frequency FROM patterns WHERE id = ?", (pattern_id,))
        row = cursor.fetchone()
        if not row:
            return 0.0
        
        query_freq = row[0]
        cursor = self.db.execute("SELECT MAX(query_frequency) FROM patterns")
        max_freq = cursor.fetchone()[0] or 1
        
        return min(1.0, query_freq / max_freq)
    
    def mark_repo_processed(self, full_name: str) -> None:
        """Mark repo as processed to avoid re-processing."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        try:
            self.db.execute(
                "INSERT INTO processed_repos (full_name, processed_at) VALUES (?, ?)",
                (full_name, now)
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            # Already processed
            pass
    
    def is_repo_processed(self, full_name: str) -> bool:
        """Check if repo has been processed."""
        cursor = self.db.execute(
            "SELECT 1 FROM processed_repos WHERE full_name = ?",
            (full_name,)
        )
        return cursor.fetchone() is not None
    
    def get_all_patterns(self, pattern_type: Optional[str] = None) -> List[StoredPattern]:
        """Get all patterns, optionally filtered by type."""
        if pattern_type:
            cursor = self.db.execute(
                "SELECT * FROM patterns WHERE type = ? ORDER BY query_frequency DESC",
                (pattern_type,)
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM patterns ORDER BY query_frequency DESC"
            )
        
        return [self._row_to_stored_pattern(row) for row in cursor.fetchall()]
    
    def deduplicate_patterns(self, patterns: List[ExtractedPattern]) -> List[ExtractedPattern]:
        """
        Deduplicate patterns using best-pick algorithm.
        
        Algorithm:
          1. Group by type
          2. For each type, get best-picks (by query frequency + reuse)
          3. Return merged, deduplicated list
        """
        if not patterns:
            return []
        
        deduped = {}
        for pattern in patterns:
            picks = self.get_best_picks(pattern.type, limit=1)
            if picks:
                # Use best-pick, skip duplicates
                best_hash = self._hash_pattern(picks[0])
                if best_hash not in deduped:
                    deduped[best_hash] = picks[0]
            else:
                # No existing picks, add new
                pattern_hash = self._hash_pattern(pattern)
                if pattern_hash not in deduped:
                    deduped[pattern_hash] = pattern
        
        return list(deduped.values())
    
    @staticmethod
    def _row_to_stored_pattern(row: tuple) -> StoredPattern:
        """Convert SQLite row to StoredPattern."""
        return StoredPattern(
            id=row[0],
            hash=row[1],
            type=row[2],
            source_repo=row[3],
            content=row[4],
            confidence=row[5],
            reusability=row[6],
            title=row[7],
            tags=json.loads(row[8]),
            reuse_count=row[9],
            query_frequency=row[10],
            first_seen=row[11],
            last_seen=row[12],
        )
    
    def close(self) -> None:
        """Close database connection."""
        if self.db:
            self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
