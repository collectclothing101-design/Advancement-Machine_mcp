"""
Emergent Behavior Observatory.

Monitors all system interactions, detects anomalous patterns, catalogs
emergent behaviors, and feeds insights back to the improvement engine.

Tracks plugin interactions, memory access patterns, tool call sequences,
and agent communication to detect behaviors that were never explicitly
programmed.
"""
import hashlib
import json
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

@dataclass
class Observation:
    obs_id: str
    timestamp: float
    source: str
    observation_type: str
    data: Dict[str, Any]
    anomaly_score: float = 0.0

class EmergentObserver:
    """Catalogs emergent behaviors by monitoring tool calls, memory access,
    agent communication, and plugin interactions for patterns that were
    never explicitly programmed."""

    def __init__(self, anomaly_threshold: float = 0.7):
        self.observations: deque = deque(maxlen=10000)
        self._call_sequences: Dict[str, List[str]] = defaultdict(list)
        self._memory_access_patterns: Dict[str, List[str]] = defaultdict(list)
        self._agent_interactions: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self._anomaly_threshold = anomaly_threshold
        self._patterns_catalog: List[Dict[str, Any]] = []

    def observe_tool_call(self, tool_name: str, arguments: dict, result: Any, agent: str = ""):
        """Record a tool call observation."""
        obs_id = hashlib.md5(f"tool:{tool_name}:{time.time()}:{hash(str(arguments))}".encode()).hexdigest()[:12]
        obs = Observation(
            obs_id=obs_id,
            timestamp=time.time(),
            source=agent or "system",
            observation_type="tool_call",
            data={"tool": tool_name, "arguments": arguments, "result_preview": str(result)[:200]},
        )
        self.observations.append(obs)
        self._call_sequences[agent or "system"].append(tool_name)
        self._detect_emergent_pattern()

    def observe_memory_access(self, agent: str, key: str, access_type: str):
        """Record a memory access observation."""
        obs_id = hashlib.md5(f"mem:{agent}:{key}:{time.time()}".encode()).hexdigest()[:12]
        obs = Observation(
            obs_id=obs_id,
            timestamp=time.time(),
            source=agent,
            observation_type="memory_access",
            data={"key": key, "access_type": access_type},
        )
        self.observations.append(obs)
        self._memory_access_patterns[agent].append(f"{access_type}:{key}")

    def observe_agent_interaction(self, agent_a: str, agent_b: str, interaction_type: str, data: dict = None):
        """Record an inter-agent interaction."""
        obs_id = hashlib.md5(f"interact:{agent_a}:{agent_b}:{time.time()}".encode()).hexdigest()[:12]
        obs = Observation(
            obs_id=obs_id,
            timestamp=time.time(),
            source=f"{agent_a}->{agent_b}",
            observation_type="agent_interaction",
            data={"type": interaction_type, "data": data or {}},
        )
        self.observations.append(obs)
        self._agent_interactions[agent_a].append((agent_b, interaction_type))

    def _detect_emergent_pattern(self):
        """Scan recent observations for repeating sequences that suggest
        emergent behavior."""
        # Check for tool call chains that repeat
        for agent, sequence in self._call_sequences.items():
            if len(sequence) >= 6:
                # Look for 3-step patterns that repeat
                for i in range(len(sequence) - 5):
                    triple = tuple(sequence[i:i+3])
                    for j in range(i+3, len(sequence) - 2):
                        if tuple(sequence[j:j+3]) == triple:
                            pattern_id = hashlib.md5(f"pattern:{agent}:{'->'.join(triple)}".encode()).hexdigest()[:8]
                            pattern = {
                                "pattern_id": pattern_id,
                                "agent": agent,
                                "sequence": list(triple),
                                "type": "tool_call_chain",
                                "occurrences": 2,
                                "first_observed": time.time(),
                            }
                            if pattern not in self._patterns_catalog:
                                self._patterns_catalog.append(pattern)
                                logger.info(f"Emergent pattern detected: {agent}: {' -> '.join(triple)}")

    def analyze_anomalies(self, window: float = 300) -> List[Dict[str, Any]]:
        """Detect anomalous observations based on frequency and type deviation."""
        now = time.time()
        recent = [o for o in self.observations if now - o.timestamp < window]

        anomalies = []
        # Check for unusually high call frequency from a single agent
        call_counts = defaultdict(int)
        for obs in recent:
            call_counts[obs.source] += 1

        for source, count in call_counts.items():
            avg = sum(call_counts.values()) / max(len(call_counts), 1)
            if count > avg * 3 and count > 10:
                anomalies.append({
                    "type": "high_frequency",
                    "source": source,
                    "count": count,
                    "expected": round(avg, 1),
                    "score": min(1.0, count / (avg * 5)),
                })

        return sorted(anomalies, key=lambda x: x["score"], reverse=True)

    def pattern_catalog(self) -> List[Dict[str, Any]]:
        return self._patterns_catalog

    def summary(self) -> dict:
        return {
            "total_observations": len(self.observations),
            "detected_patterns": len(self._patterns_catalog),
            "tracked_agents": len(set(o.source for o in self.observations)),
            "anomalies": len(self.analyze_anomalies()),
            "unique_tool_sequences": len(self._call_sequences),
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "emergent_summary",
                "description": "Get summary of emergent behaviors detected",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "emergent_anomalies",
                "description": "Detect anomalous system behavior patterns",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "window": {"type": "number", "description": "Time window in seconds", "default": 300},
                    },
                },
            },
            {
                "name": "emergent_patterns",
                "description": "Catalog of discovered emergent behavior patterns",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]