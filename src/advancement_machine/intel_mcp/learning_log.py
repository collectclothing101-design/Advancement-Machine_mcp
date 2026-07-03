"""
Learning Log: Audit trail and decision tracking.

Records:
  - Scan history
  - Suggestions applied/rejected
  - Pattern updates
  - Decision rationale
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class LearningLog:
    """Audit trail for all intel operations."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize learning log."""
        if db_path is None:
            db_path = str(Path.home() / ".advancement_machine_intel" / "learning.db")
        
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = self._init_db()
        logger.debug(f"LearningLog initialized at {db_path}")
    
    def _init_db(self) -> sqlite3.Connection:
        """Initialize learning log database."""
        db = sqlite3.connect(self.db_path)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                repos_found INTEGER NOT NULL,
                patterns_extracted INTEGER NOT NULL,
                top_patterns TEXT NOT NULL
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                suggestion_id TEXT NOT NULL,
                title TEXT NOT NULL,
                level TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                context TEXT NOT NULL,
                rationale TEXT NOT NULL
            )
        """)
        
        db.commit()
        return db
    
    def log_scan(
        self,
        query: str,
        repos_found: int,
        patterns_extracted: int,
        top_patterns: List[str]
    ) -> None:
        """Log a GitHub scan operation."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        top_patterns_json = json.dumps(top_patterns[:5])
        
        self.db.execute("""
            INSERT INTO scan_history (scan_timestamp, query, repos_found, patterns_extracted, top_patterns)
            VALUES (?, ?, ?, ?, ?)
        """, (now, query, repos_found, patterns_extracted, top_patterns_json))
        
        self.db.commit()
        logger.info(f"Logged scan: {query} ({repos_found} repos, {patterns_extracted} patterns)")
    
    def log_suggestion(
        self,
        suggestion_id: str,
        title: str,
        level: str,
        status: str,  # applied, rejected, deferred
        reason: Optional[str] = None
    ) -> None:
        """Log a suggestion decision."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        
        self.db.execute("""
            INSERT INTO suggestions_log (timestamp, suggestion_id, title, level, status, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now, suggestion_id, title, level, status, reason or ""))
        
        self.db.commit()
        logger.info(f"Logged suggestion: {title} ({status})")
    
    def log_decision(
        self,
        decision_type: str,  # pattern_adopted, pattern_rejected, stack_changed
        context: str,
        rationale: str
    ) -> None:
        """Log a strategic decision."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        
        self.db.execute("""
            INSERT INTO decisions (timestamp, decision_type, context, rationale)
            VALUES (?, ?, ?, ?)
        """, (now, decision_type, context, rationale))
        
        self.db.commit()
        logger.info(f"Logged decision: {decision_type}")
    
    def get_recent_scans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent scan history."""
        cursor = self.db.execute("""
            SELECT scan_timestamp, query, repos_found, patterns_extracted
            FROM scan_history
            ORDER BY scan_timestamp DESC
            LIMIT ?
        """, (limit,))
        
        return [
            {
                "timestamp": row[0],
                "query": row[1],
                "repos_found": row[2],
                "patterns_extracted": row[3]
            }
            for row in cursor.fetchall()
        ]
    
    def get_suggestion_summary(self) -> Dict[str, int]:
        """Get summary of suggestion decisions."""
        cursor = self.db.execute("""
            SELECT status, COUNT(*) as count
            FROM suggestions_log
            GROUP BY status
        """)
        
        return {row[0]: row[1] for row in cursor.fetchall()}
    
    def get_recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent strategic decisions."""
        cursor = self.db.execute("""
            SELECT timestamp, decision_type, context, rationale
            FROM decisions
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        return [
            {
                "timestamp": row[0],
                "type": row[1],
                "context": row[2],
                "rationale": row[3]
            }
            for row in cursor.fetchall()
        ]
    
    def close(self) -> None:
        """Close database connection."""
        if self.db:
            self.db.close()
