"""
Gist MCP Tools: GitHub Gist intelligence tools for MCP protocol.

Tools:
  - scan_public_gists: Search for high-signal public gists
  - get_user_gists: Fetch user's gists (public + authenticated secret)
  - extract_gist_patterns: Pattern discovery from gist files
  - compare_gist_patterns: Pattern comparison for relevance
  - generate_gist_suggestions: Full gist intelligence pipeline
"""

import logging
import json
from typing import Dict, Any, List, Optional

from .gist_client import GistClient, GistClientError
from .gist_collector import GistCollector
from .gitmcp_url_converter import GitMCPURLConverter
from .pattern_extractor import PatternExtractor
from .pattern_memory import PatternMemory

logger = logging.getLogger(__name__)


class GistMCPTools:
    """MCP interface to GitHub Gist intelligence engine."""

    def __init__(self, github_token: Optional[str] = None, project_path: str = "."):
        """Initialize gist MCP tools."""
        self.gist_client = GistClient(token=github_token)
        self.collector = GistCollector(self.gist_client)
        self.extractor = PatternExtractor()
        self.pattern_memory = PatternMemory()
        self.url_converter = GitMCPURLConverter()

        logger.debug("GistMCPTools initialized")

    # ═════════════════════════════════════════════════════════════════════════
    # TOOLS
    # ═════════════════════════════════════════════════════════════════════════

    async def scan_public_gists(
        self, usernames: Optional[List[str]] = None, max_gists: int = 50
    ) -> Dict[str, Any]:
        """
        Scan public gists from users.

        MCP Tool: scan_public_gists

        Args:
            usernames: Usernames to scan (default: ["github"])
            max_gists: Maximum gists to scan (default: 50)

        Returns:
            Scanned gists with patterns extracted
        """
        try:
            logger.info(f"Scanning public gists: {usernames or 'default'}")

            gists = await self.collector.collect_from_users(
                usernames=usernames, include_secret=False, max_gists=max_gists
            )

            # Extract patterns from each gist
            gists_with_patterns = []
            for gist in gists:
                patterns = self._extract_gist_patterns(gist)
                gist["patterns"] = patterns
                gist["gitmcp_url"] = self._convert_gist_url(gist)
                gists_with_patterns.append(gist)

            # Store in pattern memory for deduplication
            for gist in gists_with_patterns:
                self.pattern_memory.add_pattern(
                    content_hash=gist.get("content_hash", ""),
                    source="gist",
                    metadata={
                        "gist_id": gist["id"],
                        "url": gist["html_url"],
                        "owner": gist["owner"],
                        "description": gist["description"],
                    },
                )

            return {
                "status": "success",
                "gists_found": len(gists_with_patterns),
                "gists": gists_with_patterns,
            }

        except Exception as e:
            logger.error(f"Scan public gists failed: {e}")
            return {"status": "error", "error": str(e)}

    async def get_user_gists(
        self, username: Optional[str] = None, include_secret: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch gists for a user.

        If username is not provided, fetches gists for authenticated user
        (requires token).

        MCP Tool: get_user_gists

        Args:
            username: GitHub username (optional)
            include_secret: Include secret/private gists (requires auth)

        Returns:
            User's gists with metadata
        """
        try:
            if username:
                logger.info(f"Fetching public gists for user: {username}")
                gists = await self.collector.collect_from_users(
                    usernames=[username], include_secret=False
                )
            else:
                logger.info("Fetching authenticated user's gists")
                gists = await self.collector.collect_authenticated_user_gists(
                    include_secret=include_secret
                )

            # Convert URLs and extract patterns
            for gist in gists:
                gist["gitmcp_url"] = self._convert_gist_url(gist)
                gist["patterns"] = self._extract_gist_patterns(gist)

            return {
                "status": "success",
                "username": username or "authenticated_user",
                "gists_found": len(gists),
                "gists": gists,
            }

        except GistClientError as e:
            logger.error(f"Get user gists failed: {e}")
            return {"status": "error", "error": str(e)}

    async def extract_gist_patterns(self, gist_id: str) -> Dict[str, Any]:
        """
        Extract patterns from a specific gist.

        MCP Tool: extract_gist_patterns

        Args:
            gist_id: GitHub Gist ID

        Returns:
            Extracted patterns and metadata
        """
        try:
            logger.info(f"Extracting patterns from gist: {gist_id}")

            gist = await self.gist_client.get_gist(gist_id)

            # Extract patterns from each file
            patterns = []
            for filename, file_obj in gist.files.items():
                if file_obj.content:
                    file_patterns = self.extractor.extract_patterns(
                        file_obj.content,
                        language=file_obj.language or self._infer_language(filename),
                    )
                    for pattern in file_patterns:
                        pattern["source_file"] = filename
                        patterns.append(pattern)

            # Store in pattern memory
            self.pattern_memory.add_pattern(
                content_hash=gist.get_content_hash(),
                source="gist",
                metadata={
                    "gist_id": gist.id,
                    "url": gist.html_url,
                    "owner": gist.owner.get("login", ""),
                    "description": gist.description,
                    "file_count": len(gist.files),
                },
            )

            return {
                "status": "success",
                "gist_id": gist_id,
                "gist_url": gist.html_url,
                "gitmcp_url": GitMCPURLConverter.build_gitmcp_gist_url(
                    gist.owner.get("login", ""), gist_id
                ),
                "description": gist.description,
                "patterns_found": len(patterns),
                "patterns": patterns,
            }

        except Exception as e:
            logger.error(f"Extract gist patterns failed: {e}")
            return {"status": "error", "error": str(e)}

    async def convert_github_url(self, url: str) -> Dict[str, Any]:
        """
        Convert GitHub URL to GitMCP format.

        Supports:
          - Repository URLs: github.com → gitmcp.io
          - Gist URLs: gist.github.com → gist.gitmcp.io
          - GitHub Pages: {user}.github.io → {user}.gitmcp.io

        MCP Tool: convert_github_url

        Args:
            url: GitHub URL to convert

        Returns:
            Conversion result with GitMCP URL
        """
        try:
            converted_url = self.url_converter.convert_url(url)

            # Detect URL type
            if "gist" in url:
                url_type = "gist"
            elif ".github.io" in url or ".gitmcp.io" in url:
                url_type = "github_pages"
            else:
                url_type = "repository"

            return {
                "status": "success",
                "original_url": url,
                "gitmcp_url": converted_url,
                "url_type": url_type,
                "converted": url != converted_url,
            }

        except Exception as e:
            logger.error(f"Convert GitHub URL failed: {e}")
            return {"status": "error", "error": str(e)}

    async def generate_gist_suggestions(
        self, project_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate suggestions based on analyzing gists.

        Full intelligence pipeline: fetch gists → extract patterns → rank → suggest

        MCP Tool: generate_gist_suggestions

        Args:
            project_analysis: Optional project analysis for context

        Returns:
            Recommendations and insights
        """
        try:
            logger.info("Generating gist suggestions")

            # Scan public gists
            scan_result = await self.scan_public_gists(max_gists=30)

            if scan_result["status"] != "success":
                return scan_result

            gists = scan_result.get("gists", [])

            # Rank by relevance (recency + pattern count)
            ranked = sorted(
                gists,
                key=lambda g: (
                    len(g.get("patterns", [])),
                    g.get("updated_at", ""),
                ),
                reverse=True,
            )

            suggestions = []
            for gist in ranked[:10]:
                suggestion = {
                    "gist_id": gist["id"],
                    "description": gist.get("description", ""),
                    "owner": gist.get("owner", ""),
                    "github_url": gist["html_url"],
                    "gitmcp_url": gist.get("gitmcp_url", ""),
                    "pattern_count": len(gist.get("patterns", [])),
                    "files": len(gist.get("files", [])),
                    "updated": gist.get("updated_at", ""),
                    "relevance_score": len(gist.get("patterns", [])) * 10,
                }
                suggestions.append(suggestion)

            return {
                "status": "success",
                "suggestions_generated": len(suggestions),
                "suggestions": suggestions,
                "total_gists_analyzed": len(gists),
            }

        except Exception as e:
            logger.error(f"Generate gist suggestions failed: {e}")
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═════════════════════════════════════════════════════════════════════════

    def _extract_gist_patterns(self, gist_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract patterns from gist dictionary."""
        # This would be populated by the MCP tools when fetching full gist content
        # For now, return empty list (patterns require file content)
        return []

    def _convert_gist_url(self, gist_dict: Dict[str, Any]) -> str:
        """Convert gist dict to GitMCP URL."""
        return GitMCPURLConverter.build_gitmcp_gist_url(
            gist_dict.get("owner", ""), gist_dict.get("id", "")
        )

    def _infer_language(self, filename: str) -> Optional[str]:
        """Infer programming language from filename."""
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".sh": "shell",
            ".bash": "bash",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
        }

        for ext, lang in ext_to_lang.items():
            if filename.endswith(ext):
                return lang

        return None
