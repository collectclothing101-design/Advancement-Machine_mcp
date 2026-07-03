"""
GitHub Collector: Multi-topic repository discovery and ranking.

Features:
  - Multi-query repository search
  - Ranking by relevance scores
  - Metadata extraction from search results
  - Deduplication of results
"""

import logging
from typing import List, Dict, Any, Optional
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


class RepositoryCollector:
    """Collects and ranks repositories from GitHub."""
    
    DEFAULT_TOPICS = [
        "mcp", "ai", "skills", "plugins", "hermes",
        "claude", "code", "development", "automation"
    ]
    
    def __init__(self, github_client: GitHubClient):
        """Initialize collector with GitHub client."""
        self.client = github_client
        logger.debug("RepositoryCollector initialized")
    
    def collect_by_topics(
        self,
        topics: Optional[List[str]] = None,
        max_repos: int = 100,
        min_stars: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Collect repositories by multiple topics.
        
        Args:
            topics: Topics to search (default: DEFAULT_TOPICS)
            max_repos: Maximum repos to collect
            min_stars: Minimum stars filter
        
        Returns:
            List of deduplicated repository dictionaries
        """
        if topics is None:
            topics = self.DEFAULT_TOPICS
        
        repos_dict = {}  # Use dict for deduplication by full_name
        
        for topic in topics:
            try:
                logger.debug(f"Searching topic: {topic}")
                search_result = self.client.search_repositories(
                    query=f"topic:{topic}",
                    sort="stars",
                    order="desc",
                    per_page=min(max_repos, 100)
                )
                
                items = search_result.get("items", [])
                for repo in items:
                    if repo["stargazers_count"] >= min_stars:
                        full_name = repo["full_name"]
                        if full_name not in repos_dict:
                            repos_dict[full_name] = {
                                "full_name": repo["full_name"],
                                "owner": repo["owner"]["login"],
                                "name": repo["name"],
                                "description": repo.get("description", ""),
                                "url": repo["html_url"],
                                "stars": repo["stargazers_count"],
                                "forks": repo["forks_count"],
                                "open_issues": repo["open_issues_count"],
                                "language": repo.get("language"),
                                "topics": repo.get("topics", []),
                                "last_updated": repo["updated_at"],
                                "created_at": repo["created_at"]
                            }
                    
                    if len(repos_dict) >= max_repos:
                        break
                
                if len(repos_dict) >= max_repos:
                    break
            
            except Exception as e:
                logger.warning(f"Error searching topic {topic}: {e}")
                continue
        
        # Sort by stars
        sorted_repos = sorted(repos_dict.values(), key=lambda r: r["stars"], reverse=True)
        logger.info(f"Collected {len(sorted_repos)} unique repositories")
        return sorted_repos
    
    def collect_by_search(
        self,
        query: str,
        max_repos: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Collect repositories by search query.
        
        Args:
            query: Search query
            max_repos: Maximum repos to collect
        
        Returns:
            List of repository dictionaries
        """
        try:
            logger.debug(f"Searching query: {query}")
            search_result = self.client.search_repositories(
                query=query,
                sort="stars",
                order="desc",
                per_page=min(max_repos, 100)
            )
            
            repos = []
            for repo in search_result.get("items", []):
                repos.append({
                    "full_name": repo["full_name"],
                    "owner": repo["owner"]["login"],
                    "name": repo["name"],
                    "description": repo.get("description", ""),
                    "url": repo["html_url"],
                    "stars": repo["stargazers_count"],
                    "forks": repo["forks_count"],
                    "open_issues": repo["open_issues_count"],
                    "language": repo.get("language"),
                    "topics": repo.get("topics", []),
                    "last_updated": repo["updated_at"],
                    "created_at": repo["created_at"]
                })
                if len(repos) >= max_repos:
                    break
            
            logger.info(f"Collected {len(repos)} repositories for query: {query}")
            return repos
        
        except Exception as e:
            logger.error(f"Error collecting repositories: {e}")
            return []
