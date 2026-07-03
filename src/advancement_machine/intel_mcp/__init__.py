"""
Intel MCP: GitHub Intelligence Layer for Advancement Machine

Modules:
  - github_client: GitHub REST API wrapper with rate limiting
  - github_collector: Repository discovery and collection
  - pattern_memory: SQLite-based pattern storage with deduplication (commit 31e6cff)
  - pattern_extractor: Extract patterns from repos
  - repo_classifier: Classify repos by relevance
  - relevance_scorer: 5-factor scoring model
  - dna_profiler: Local tech stack detection
  - comparator: Gap analysis between repos
  - suggestion_engine: Generate improvement suggestions
  - patch_builder: Build safe unified diffs
  - learning_log: Audit trail & decision tracking
  - mcp_tools: MCP interface to intelligence engine

Key Features (Commit 31e6cff):
  ✅ Query frequency scoring (prevent duplicate suggestions)
  ✅ Best-pick deduplication algorithm
  ✅ PatternMemory wiring (unified SQLite backend)
"""

from .github_client import GitHubClient
from .pattern_memory import PatternMemory, StoredPattern, ExtractedPattern
from .repo_classifier import RepoClassifier
from .relevance_scorer import RelevanceScorer
from .pattern_extractor import PatternExtractor
from .dna_profiler import DNAProfiler
from .comparator import Comparator
from .suggestion_engine import SuggestionEngine, Suggestion, SuggestionLevel
from .patch_builder import PatchBuilder
from .learning_log import LearningLog
from .mcp_tools import IntelMCPTools
from .github_collector import RepositoryCollector

__all__ = [
    "GitHubClient",
    "RepositoryCollector",
    "PatternMemory",
    "StoredPattern",
    "ExtractedPattern",
    "RepoClassifier",
    "RelevanceScorer",
    "PatternExtractor",
    "DNAProfiler",
    "Comparator",
    "SuggestionEngine",
    "Suggestion",
    "SuggestionLevel",
    "PatchBuilder",
    "LearningLog",
    "IntelMCPTools",
]
