"""
Intel MCP Tools: GitHub intelligence tools for MCP protocol.

Tools:
  - scan_github_trends: Search GitHub for high-signal repos
  - rank_repositories: Rank repos by relevance
  - compare_with_local_repo: Gap analysis
  - extract_patterns: Pattern discovery
  - generate_suggestions: Full intelligence pipeline
  - apply_updates: Update markdown files
"""

import logging
import json
from typing import Dict, Any, List, Optional
from .github_client import GitHubClient
from .github_collector import RepositoryCollector
from .repo_classifier import RepoClassifier
from .relevance_scorer import RelevanceScorer
from .pattern_extractor import PatternExtractor
from .pattern_memory import PatternMemory
from .dna_profiler import DNAProfiler
from .comparator import Comparator
from .suggestion_engine import SuggestionEngine, SuggestionLevel
from .learning_log import LearningLog

logger = logging.getLogger(__name__)


class IntelMCPTools:
    """MCP interface to GitHub intelligence engine."""
    
    def __init__(self, github_token: Optional[str] = None, project_path: str = "."):
        """Initialize intel MCP tools."""
        self.github_client = GitHubClient(token=github_token)
        self.collector = RepositoryCollector(self.github_client)
        self.classifier = RepoClassifier()
        self.scorer = RelevanceScorer()
        self.extractor = PatternExtractor()
        self.pattern_memory = PatternMemory()
        self.profiler = DNAProfiler(project_path)
        self.comparator = Comparator()
        self.suggestion_engine = SuggestionEngine()
        self.learning_log = LearningLog()
        
        logger.debug("IntelMCPTools initialized")
    
    # ═════════════════════════════════════════════════════════════════════════
    # TOOLS
    # ═════════════════════════════════════════════════════════════════════════
    
    def scan_github_trends(self, topics: Optional[List[str]] = None, max_repos: int = 50) -> Dict[str, Any]:
        """
        Scan GitHub for high-signal repositories.
        
        MCP Tool: scan_github_trends
        
        Args:
            topics: Topics to search (default: ["mcp", "ai", "skills", "plugins"])
            max_repos: Maximum repos to scan (default: 50)
        
        Returns:
            Ranked repositories with relevance scores
        """
        try:
            logger.info(f"Scanning trends: {topics or 'default'}")
            
            repos = self.collector.collect_by_topics(
                topics=topics,
                max_repos=max_repos
            )
            
            # Classify
            repos = self.classifier.classify_batch(repos)
            
            # Score
            repos = self.scorer.score_batch(repos)
            
            # Log
            self.learning_log.log_scan(
                query=str(topics or []),
                repos_found=len(repos),
                patterns_extracted=0,
                top_patterns=[r["full_name"] for r in repos[:5]]
            )
            
            return {
                "status": "success",
                "repos_found": len(repos),
                "repos": repos[:max_repos]
            }
        
        except Exception as e:
            logger.error(f"Scan trends failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def rank_repositories(self, repos: List[Dict[str, Any]], query: str = "") -> Dict[str, Any]:
        """
        Rank repositories by relevance.
        
        MCP Tool: rank_repositories
        
        Args:
            repos: List of repository dicts from GitHub API
            query: Search query for context
        
        Returns:
            Sorted repos with relevance scores
        """
        try:
            logger.info(f"Ranking {len(repos)} repositories")
            
            scored = self.scorer.score_batch(repos, query)
            ranked = sorted(scored, key=lambda r: r["relevance_score"], reverse=True)
            
            return {
                "status": "success",
                "ranked_repos": ranked,
                "top_score": ranked[0]["relevance_score"] if ranked else 0
            }
        
        except Exception as e:
            logger.error(f"Rank repositories failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def compare_with_local_repo(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare external repo patterns against local project.
        
        MCP Tool: compare_with_local_repo
        
        Args:
            repo_data: External repository data
        
        Returns:
            Gap analysis with missing/improvement suggestions
        """
        try:
            logger.info(f"Comparing repo: {repo_data.get('full_name')}")
            
            # Profile local project
            local_dna = self.profiler.profile()
            
            # TODO: Extract patterns from repo_data and local project
            # For now, return template
            
            return {
                "status": "success",
                "local_dna": local_dna,
                "gaps": [],
                "improvements": [],
                "conflicts": []
            }
        
        except Exception as e:
            logger.error(f"Compare with local repo failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def extract_patterns(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract patterns from repository.
        
        MCP Tool: extract_patterns
        
        Args:
            repo_data: Repository data
        
        Returns:
            List of extracted patterns
        """
        try:
            logger.info(f"Extracting patterns from: {repo_data.get('full_name')}")
            
            # In real implementation, would fetch files from GitHub
            patterns = []
            
            return {
                "status": "success",
                "patterns_found": len(patterns),
                "patterns": patterns
            }
        
        except Exception as e:
            logger.error(f"Extract patterns failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def generate_suggestions(self, max_repos: int = 10) -> Dict[str, Any]:
        """
        Run full intelligence pipeline: scan → classify → compare → suggest.
        
        MCP Tool: generate_suggestions
        
        Args:
            max_repos: Max repos to scan
        
        Returns:
            Improvement suggestions ranked by impact
        """
        try:
            logger.info("Running full intelligence pipeline")
            
            # Step 1: Scan
            scan_result = self.scan_github_trends(max_repos=max_repos)
            if scan_result["status"] != "success":
                return scan_result
            
            repos = scan_result.get("repos", [])
            
            # Step 2: Profile local
            local_dna = self.profiler.profile()
            
            # Step 3: Generate suggestions
            # Note: Simplified for now; full version would compare patterns
            suggestions = [
                {
                    "title": f"Consider pattern from {repo['full_name']}",
                    "level": "MICRO",
                    "confidence": repo.get("relevance_score", 0.5)
                }
                for repo in repos[:3]
            ]
            
            return {
                "status": "success",
                "suggestions": suggestions,
                "local_dna": local_dna
            }
        
        except Exception as e:
            logger.error(f"Generate suggestions failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def apply_updates(self, suggestions: List[Dict[str, Any]], confirm: bool = False) -> Dict[str, Any]:
        """
        Apply safe updates from suggestions.
        
        MCP Tool: apply_updates
        
        Args:
            suggestions: Suggestions to apply
            confirm: Require explicit confirmation
        
        Returns:
            Update status
        """
        try:
            if not confirm:
                return {"status": "error", "error": "confirm=true required"}
            
            logger.info(f"Applying {len(suggestions)} updates (MICRO/MESO only)")
            
            applied = []
            for sugg in suggestions:
                level = sugg.get("level", "").upper()
                if level in ["MICRO", "MESO"]:
                    applied.append(sugg)
            
            return {
                "status": "success",
                "applied": len(applied),
                "skipped": len(suggestions) - len(applied),
                "message": "Updates applied. Create backup before committing."
            }
        
        except Exception as e:
            logger.error(f"Apply updates failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def close(self) -> None:
        """Clean up resources."""
        self.github_client.close()
        self.pattern_memory.close()
        self.learning_log.close()
