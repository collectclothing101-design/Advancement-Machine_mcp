"""
GitHub Gist Collector: Multi-user/topic gist discovery and ranking.

Features:
  - Public gist collection from users
  - Secret gist access (with authentication)
  - Pattern extraction from gist files
  - Metadata deduplication using SHA256 hash
  - Ranking by relevance and recency
"""

import logging
from typing import List, Dict, Any, Optional
from .gist_client import GistClient, GitHubGist, GistClientError

logger = logging.getLogger(__name__)


class GistCollector:
    """Collects and ranks gists from GitHub."""

    DEFAULT_USERS = [
        "github",  # Official GitHub gists
        # Add more seed users as needed
    ]

    def __init__(self, gist_client: GistClient):
        """Initialize collector with Gist client."""
        self.client = gist_client
        logger.debug("GistCollector initialized")

    async def collect_from_users(
        self,
        usernames: Optional[List[str]] = None,
        include_secret: bool = False,
        max_gists: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Collect gists from multiple users.

        Args:
            usernames: List of GitHub usernames (default: DEFAULT_USERS)
            include_secret: Include secret/private gists (requires auth)
            max_gists: Maximum total gists to collect

        Returns:
            List of deduplicated gist dictionaries
        """
        if usernames is None:
            usernames = self.DEFAULT_USERS

        gists_dict = {}  # Use dict for deduplication by gist ID

        for username in usernames:
            try:
                logger.debug(f"Collecting gists from {username}")
                gists = await self.client.list_user_gists(
                    username=username, include_secret=include_secret
                )

                for gist in gists:
                    if gist.id not in gists_dict:
                        gist_dict = self._gist_to_dict(gist)
                        gists_dict[gist.id] = gist_dict

                    if len(gists_dict) >= max_gists:
                        break

                if len(gists_dict) >= max_gists:
                    break

            except GistClientError as e:
                logger.warning(f"Error collecting from {username}: {e}")
                continue

        # Sort by updated_at (newest first)
        sorted_gists = sorted(
            gists_dict.values(), key=lambda g: g["updated_at"], reverse=True
        )
        logger.info(f"Collected {len(sorted_gists)} unique gists")
        return sorted_gists

    async def collect_authenticated_user_gists(
        self, include_secret: bool = True, max_gists: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Collect gists for authenticated user (requires token).

        Args:
            include_secret: Include secret/private gists
            max_gists: Maximum gists to collect

        Returns:
            List of gist dictionaries

        Raises:
            GistClientError: If authentication fails
        """
        try:
            logger.debug("Collecting authenticated user's gists")
            gists = await self.client.list_user_gists(
                username=None, include_secret=include_secret
            )

            gist_dicts = [self._gist_to_dict(gist) for gist in gists[:max_gists]]
            logger.info(f"Collected {len(gist_dicts)} gists for authenticated user")
            return gist_dicts

        except Exception as e:
            logger.error(f"Failed to collect authenticated user gists: {e}")
            return []

    async def collect_by_pattern(
        self, username: str, file_pattern: str, max_gists: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Collect gists from a user that contain files matching a pattern.

        Args:
            username: GitHub username
            file_pattern: Filename pattern (e.g., "*.py", "*config*")
            max_gists: Maximum gists to collect

        Returns:
            List of matching gist dictionaries
        """
        try:
            logger.debug(f"Collecting gists from {username} with files matching {file_pattern}")
            gists = await self.client.list_user_gists(username=username, include_secret=False)

            matching_gists = []
            for gist in gists:
                # Check if any file matches pattern
                for filename in gist.files.keys():
                    if self._matches_pattern(filename, file_pattern):
                        gist_dict = self._gist_to_dict(gist)
                        matching_gists.append(gist_dict)
                        break

                if len(matching_gists) >= max_gists:
                    break

            logger.info(f"Found {len(matching_gists)} gists matching pattern {file_pattern}")
            return matching_gists

        except Exception as e:
            logger.error(f"Error collecting by pattern: {e}")
            return []

    def _gist_to_dict(self, gist: GitHubGist) -> Dict[str, Any]:
        """Convert GitHubGist to dictionary format."""
        file_list = []
        for filename, file_obj in gist.files.items():
            file_list.append({
                "filename": filename,
                "type": file_obj.type,
                "language": file_obj.language,
                "size": file_obj.size,
                "raw_url": file_obj.raw_url,
            })

        return {
            "id": gist.id,
            "url": gist.url,
            "html_url": gist.html_url,
            "owner": gist.owner.get("login", ""),
            "description": gist.description or "",
            "public": gist.public,
            "comments": gist.comments,
            "created_at": gist.created_at,
            "updated_at": gist.updated_at,
            "files": file_list,
            "file_count": len(gist.files),
            "content_hash": gist.get_content_hash(),
        }

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """
        Check if filename matches pattern.

        Supports wildcards (* and ?)

        Args:
            filename: Filename to check
            pattern: Pattern with wildcards

        Returns:
            True if matches
        """
        import fnmatch

        return fnmatch.fnmatch(filename, pattern)
