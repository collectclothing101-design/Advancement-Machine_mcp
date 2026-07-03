"""
Patch Builder: Generate safe unified diffs for MD files.

Features:
  - Non-destructive patches (append-only)
  - Unified diff format
  - Safety annotations
  - Backup creation
"""

import difflib
import logging
from typing import List, Tuple
from .suggestion_engine import Suggestion, SuggestionLevel

logger = logging.getLogger(__name__)


class PatchBuilder:
    """Build safe patches for file modifications."""
    
    def __init__(self):
        logger.debug("PatchBuilder initialized")
    
    def build_patch(self, suggestion: Suggestion) -> str:
        """
        Build unified diff patch from suggestion.
        
        Returns:
            Unified diff format string
        """
        if suggestion.level == SuggestionLevel.MICRO:
            return self._build_micro_patch(suggestion)
        elif suggestion.level == SuggestionLevel.MESO:
            return self._build_meso_patch(suggestion)
        else:
            return self._build_macro_patch(suggestion)
    
    def _build_micro_patch(self, suggestion: Suggestion) -> str:
        """Build single-line patch."""
        lines = [
            f"--- {suggestion.target_file}",
            f"+++ {suggestion.target_file} (MICRO)",
            "@@ -1,1 +1,2 @@",
            f"+ <!-- intel: {suggestion.title} -->",
            f"+ {suggestion.content[:100]}",
            ""
        ]
        return "\n".join(lines)
    
    def _build_meso_patch(self, suggestion: Suggestion) -> str:
        """Build section patch."""
        lines = [
            f"--- {suggestion.target_file}",
            f"+++ {suggestion.target_file} (MESO)",
            "@@ -1,1 +1,10 @@",
            f"+ ## {suggestion.title}",
            f"+",
            f"+ {suggestion.description}",
            f"+",
            f"+ ```",
            f"+ {suggestion.content[:200]}",
            f"+ ```",
            ""
        ]
        return "\n".join(lines)
    
    def _build_macro_patch(self, suggestion: Suggestion) -> str:
        """Build major restructuring patch (review required)."""
        lines = [
            "# MACRO PATCH - REQUIRES MANUAL REVIEW",
            f"Title: {suggestion.title}",
            f"Description: {suggestion.description}",
            f"Risk Level: {suggestion.risk.upper()}",
            f"Target File: {suggestion.target_file}",
            "",
            "## Suggested Changes",
            "```",
            suggestion.content[:500],
            "```",
            "",
            "## Safety Checklist",
            "- [ ] Reviewed with team",
            "- [ ] Tested in isolation",
            "- [ ] Backward compatibility verified",
            "- [ ] Documentation updated",
            ""
        ]
        return "\n".join(lines)
    
    def generate_patch_preview(self, original: str, suggestion: Suggestion) -> str:
        """
        Generate before/after diff.
        
        Args:
            original: Original file content
            suggestion: Suggested modification
        
        Returns:
            Unified diff preview
        """
        original_lines = original.split("\n")
        suggested_lines = (original + "\n\n" + suggestion.content).split("\n")
        
        diff = difflib.unified_diff(
            original_lines,
            suggested_lines,
            fromfile=suggestion.target_file,
            tofile=f"{suggestion.target_file}.suggested",
            lineterm=""
        )
        
        return "\n".join(diff)
