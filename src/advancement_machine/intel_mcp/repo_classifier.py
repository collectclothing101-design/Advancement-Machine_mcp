"""
Repository Classifier: Classify repositories by relevance tags.

Tags: mcp, plugin, skill, ai-ready, active, maintained, hermes, claude, etc.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class RepoClassifier:
    """Classify repositories by relevance."""
    
    TAG_KEYWORDS = {
        "mcp": ["mcp", "protocol", "model context"],
        "plugin": ["plugin", "extension", "addon"],
        "skill": ["skill", "capabilities", "ability"],
        "ai-ready": ["ai", "llm", "agent", "claude", "gpt"],
        "active": ["maintained", "active development", "up to date"],
        "maintained": ["maintained", "actively maintained", "recent"],
        "hermes": ["hermes", "advancement machine"],
        "claude": ["claude", "anthropic"],
        "github-tools": ["github", "git", "repository", "vcs"],
    }
    
    def __init__(self):
        """Initialize classifier."""
        logger.debug("RepoClassifier initialized")
    
    def classify(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify repository.
        
        Args:
            repo: Repository data from GitHub
        
        Returns:
            Repo with added 'tags' list
        """
        text = (
            repo.get("name", "").lower() +
            " " +
            repo.get("description", "").lower() +
            " " +
            " ".join(repo.get("topics", []))
        ).lower()
        
        tags = []
        
        # Check keywords
        for tag, keywords in self.TAG_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    if tag not in tags:
                        tags.append(tag)
                    break
        
        # Activity check
        if repo.get("stargazers_count", 0) >= 100:
            if "popular" not in tags:
                tags.append("popular")
        
        repo["tags"] = tags
        logger.debug(f"Classified {repo['full_name']}: {tags}")
        return repo
    
    def classify_batch(self, repos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify multiple repositories."""
        return [self.classify(repo) for repo in repos]
