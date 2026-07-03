"""
Relevance Scorer: 5-factor scoring model for repositories.

Factors:
  1. Activity (stars, forks, recent updates)
  2. Maturity (age, stability indicators)
  3. Quality (open issues, language diversity)
  4. Community (watchers, network)
  5. Relevance (keyword match to queries)
"""

import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RelevanceScorer:
    """Score repositories by relevance (0-1)."""
    
    def __init__(self):
        logger.debug("RelevanceScorer initialized")
    
    def score(self, repo: Dict[str, Any], query: str = "") -> float:
        """
        Score repository relevance (0-1).
        
        Factors:
          1. Activity (40%): stars + forks + recent
          2. Maturity (20%): age + stability
          3. Quality (15%): issues ratio
          4. Community (10%): engagement
          5. Relevance (15%): keyword match
        """
        activity = self._score_activity(repo)  # 0-1
        maturity = self._score_maturity(repo)  # 0-1
        quality = self._score_quality(repo)    # 0-1
        community = self._score_community(repo)  # 0-1
        relevance = self._score_relevance(repo, query)  # 0-1
        
        # Weighted average
        score = (
            activity * 0.40 +
            maturity * 0.20 +
            quality * 0.15 +
            community * 0.10 +
            relevance * 0.15
        )
        
        return min(1.0, max(0.0, score))
    
    def _score_activity(self, repo: Dict[str, Any]) -> float:
        """Score activity (recent updates, stars, forks)."""
        stars = min(repo.get("stargazers_count", 0) / 1000, 1.0)
        forks = min(repo.get("forks_count", 0) / 500, 1.0)
        
        # Check last update (within 3 months = 1.0)
        try:
            last_update = datetime.fromisoformat(repo["last_updated"].replace("Z", "+00:00"))
            days_since = (datetime.now(last_update.tzinfo) - last_update).days
            recent = max(0.0, 1.0 - (days_since / 90))
        except:
            recent = 0.5
        
        return (stars * 0.5 + forks * 0.3 + recent * 0.2)
    
    def _score_maturity(self, repo: Dict[str, Any]) -> float:
        """Score maturity (age, stability)."""
        try:
            created_at = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
            age_days = (datetime.now(created_at.tzinfo) - created_at).days
            age_score = min(1.0, age_days / 730)  # 2 years = max
        except:
            age_score = 0.5
        
        # Language presence (typed languages score higher)
        language = repo.get("language", "").lower()
        lang_score = 0.8 if language in ["python", "typescript", "go", "rust"] else 0.5 if language else 0.3
        
        return (age_score * 0.6 + lang_score * 0.4)
    
    def _score_quality(self, repo: Dict[str, Any]) -> float:
        """Score quality (issues, maintenance)."""
        issues = repo.get("open_issues", 0)
        stars = repo.get("stargazers_count", 0)
        
        # Issues per 100 stars
        if stars > 0:
            issues_ratio = min(1.0, issues / (stars / 10))
            issue_score = max(0.0, 1.0 - issues_ratio)
        else:
            issue_score = 0.5
        
        return issue_score
    
    def _score_community(self, repo: Dict[str, Any]) -> float:
        """Score community (engagement)."""
        watchers = repo.get("watchers_count", 0)
        forks = repo.get("forks_count", 0)
        
        engagement = min(1.0, (watchers + forks) / 100)
        return engagement
    
    def _score_relevance(self, repo: Dict[str, Any], query: str) -> float:
        """Score keyword relevance."""
        if not query:
            return 0.5
        
        text = (
            repo.get("name", "").lower() +
            " " +
            repo.get("description", "").lower() +
            " " +
            " ".join(repo.get("topics", []))
        ).lower()
        
        query_terms = query.lower().split()
        matches = sum(1 for term in query_terms if term in text)
        
        relevance = min(1.0, matches / len(query_terms)) if query_terms else 0.5
        return relevance
    
    def score_batch(self, repos: list, query: str = "") -> list:
        """Score multiple repositories."""
        scored = []
        for repo in repos:
            repo_score = self.score(repo, query)
            repo["relevance_score"] = repo_score
            scored.append(repo)
        
        # Sort by score descending
        return sorted(scored, key=lambda r: r["relevance_score"], reverse=True)
