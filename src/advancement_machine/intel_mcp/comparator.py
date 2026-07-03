"""
Comparator: Gap analysis between external repos and local project.

Identifies:
  - Missing patterns (what to adopt)
  - Improvements (what to improve)
  - Conflicts (what to be careful about)
"""

import logging
from typing import List, Dict, Any
from .pattern_memory import StoredPattern

logger = logging.getLogger(__name__)


class Comparator:
    """Compare external repos against local project."""
    
    def __init__(self):
        logger.debug("Comparator initialized")
    
    def compare(
        self,
        external_patterns: List[StoredPattern],
        local_patterns: List[StoredPattern],
        local_dna: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare external patterns against local project.
        
        Returns:
            Dict with:
              - missing: patterns not in local project
              - improvements: enhancements to existing patterns
              - conflicts: incompatibilities to watch
              - fit_score: 0-1 compatibility score
        """
        external_hashes = {self._hash_pattern(p) for p in external_patterns}
        local_hashes = {self._hash_pattern(p) for p in local_patterns}
        
        missing_hashes = external_hashes - local_hashes
        improvement_hashes = external_hashes & local_hashes
        
        missing = [p for p in external_patterns if self._hash_pattern(p) in missing_hashes]
        improvements = [p for p in external_patterns if self._hash_pattern(p) in improvement_hashes]
        
        conflicts = self._find_conflicts(external_patterns, local_dna)
        
        fit_score = self._calculate_fit_score(len(missing), len(improvements), len(conflicts))
        
        return {
            "missing": missing,
            "improvements": improvements,
            "conflicts": conflicts,
            "fit_score": fit_score,
            "gap_size": len(missing)
        }
    
    def _hash_pattern(self, pattern: StoredPattern) -> str:
        """Simple hash for pattern comparison."""
        return f"{pattern.type}::{pattern.title}"
    
    def _find_conflicts(self, patterns: List[StoredPattern], local_dna: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find potential conflicts with local stack."""
        conflicts = []
        local_frameworks = local_dna.get("frameworks", [])
        
        for pattern in patterns:
            # Check for incompatible framework combinations
            if "django" in pattern.tags and "fastapi" in local_frameworks:
                conflicts.append({
                    "pattern": pattern.title,
                    "conflict": "Django patterns may not align with FastAPI",
                    "severity": "warning"
                })
        
        return conflicts
    
    def _calculate_fit_score(self, missing: int, improvements: int, conflicts: int) -> float:
        """Calculate how well external repo fits local project."""
        total = max(1, missing + improvements)
        fit = improvements / total if total > 0 else 0.5
        
        # Reduce for conflicts
        conflict_penalty = min(0.3, conflicts * 0.1)
        
        return max(0.0, fit - conflict_penalty)
