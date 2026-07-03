"""
Suggestion Engine: Generate improvement suggestions.

Suggestion levels:
  - MICRO: Add a single config line
  - MESO: Update a file section
  - MACRO: Restructure entire component
"""

import logging
from typing import List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SuggestionLevel(Enum):
    """Suggestion complexity level."""
    MICRO = "micro"      # Single line changes
    MESO = "meso"        # Section updates
    MACRO = "macro"      # Major restructuring


class Suggestion:
    """Improvement suggestion."""
    
    def __init__(
        self,
        title: str,
        description: str,
        level: SuggestionLevel,
        target_file: str,
        content: str,
        confidence: float,
        risk: str = "low"
    ):
        self.title = title
        self.description = description
        self.level = level
        self.target_file = target_file
        self.content = content
        self.confidence = confidence
        self.risk = risk  # low, medium, high


class SuggestionEngine:
    """Generate improvement suggestions."""
    
    def __init__(self):
        logger.debug("SuggestionEngine initialized")
    
    def generate(
        self,
        gap_analysis: Dict[str, Any]
    ) -> List[Suggestion]:
        """
        Generate suggestions from gap analysis.
        
        Args:
            gap_analysis: Output from Comparator.compare()
        
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        missing_patterns = gap_analysis.get("missing", [])
        improvements = gap_analysis.get("improvements", [])
        conflicts = gap_analysis.get("conflicts", [])
        
        # Generate suggestions from missing patterns
        for pattern in missing_patterns:
            sugg = self._suggest_for_missing(pattern)
            if sugg:
                suggestions.append(sugg)
        
        # Generate suggestions for improvements
        for pattern in improvements:
            sugg = self._suggest_for_improvement(pattern)
            if sugg:
                suggestions.append(sugg)
        
        # Generate warnings for conflicts
        for conflict in conflicts:
            sugg = self._suggest_for_conflict(conflict)
            if sugg:
                suggestions.append(sugg)
        
        # Sort by level (micro first, safer to apply)
        level_order = {SuggestionLevel.MICRO: 0, SuggestionLevel.MESO: 1, SuggestionLevel.MACRO: 2}
        suggestions.sort(key=lambda s: (level_order[s.level], -s.confidence))
        
        logger.info(f"Generated {len(suggestions)} suggestions")
        return suggestions
    
    def _suggest_for_missing(self, pattern) -> Suggestion:
        """Generate suggestion to add missing pattern."""
        target_file = self._infer_target_file(pattern)
        
        level = SuggestionLevel.MICRO if len(pattern.content) < 100 else SuggestionLevel.MESO
        
        return Suggestion(
            title=f"Add: {pattern.title}",
            description=f"Missing pattern: {pattern.type}. Found in high-signal repos. Confidence: {pattern.confidence:.0%}",
            level=level,
            target_file=target_file,
            content=pattern.content,
            confidence=pattern.confidence,
            risk="low" if level == SuggestionLevel.MICRO else "medium"
        )
    
    def _suggest_for_improvement(self, pattern) -> Suggestion:
        """Generate suggestion to improve existing pattern."""
        return Suggestion(
            title=f"Enhance: {pattern.title}",
            description=f"Pattern exists but could be improved. Current reusability: {pattern.reusability:.0%}",
            level=SuggestionLevel.MESO,
            target_file=self._infer_target_file(pattern),
            content=pattern.content,
            confidence=pattern.reusability,
            risk="medium"
        )
    
    def _suggest_for_conflict(self, conflict) -> Suggestion:
        """Generate warning for conflict."""
        return Suggestion(
            title=f"Review: {conflict.get('conflict', 'Potential Issue')}",
            description=f"Pattern may conflict with local setup. Severity: {conflict.get('severity', 'info')}",
            level=SuggestionLevel.MACRO,
            target_file="REVIEW_REQUIRED",
            content=conflict.get('conflict', ''),
            confidence=0.5,
            risk="high"
        )
    
    def _infer_target_file(self, pattern) -> str:
        """Infer which file to modify for pattern."""
        if pattern.type == "config":
            return "Advancement-Machine-intel.md"
        elif pattern.type == "architecture":
            return "README.md"
        elif pattern.type == "workflow":
            return ".github/workflows/ci.yml"
        else:
            return "Advancement-Machine-intel.md"
