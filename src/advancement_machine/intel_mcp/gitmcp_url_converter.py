"""
GitMCP URL Converter: Convert GitHub URLs to GitMCP domain format.

Converts:
  - github.com → gitmcp.io
  - {owner}.github.io → {owner}.gitmcp.io
  - gist.github.com → gist.gitmcp.io
  - gist.github.io → gist.gitmcp.io

Supports:
  - Repository URLs
  - User profile URLs
  - Gist URLs (public and secret)
  - GitHub Pages URLs
  - Raw content URLs
"""

import logging
import re
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

# URL pattern mappings
DOMAIN_MAPPINGS = {
    # Repository URLs
    r"^https?://github\.com/": "https://gitmcp.io/",
    # User/org gists
    r"^https?://gist\.github\.com/": "https://gist.gitmcp.io/",
    # GitHub Pages
    r"^https?://([a-zA-Z0-9_-]+)\.github\.io/": r"https://\1.gitmcp.io/",
    r"^https?://([a-zA-Z0-9_-]+)\.gist\.github\.io/": r"https://\1.gist.gitmcp.io/",
}

# Regex patterns for URL detection
URL_PATTERN = re.compile(r"(https?://[^\s\)]+)")
GITHUB_URL_PATTERN = re.compile(
    r"https?://(www\.)?(github\.com|gist\.github\.com|([a-zA-Z0-9_-]+\.)?(github\.io|gist\.github\.io))"
)


class GitMCPURLConverter:
    """Convert GitHub URLs to GitMCP domain format."""

    @staticmethod
    def convert_url(url: str) -> str:
        """
        Convert a GitHub URL to GitMCP format.

        Args:
            url: GitHub URL to convert

        Returns:
            Converted GitMCP URL

        Example:
            >>> converter = GitMCPURLConverter()
            >>> converter.convert_url("https://github.com/owner/repo")
            'https://gitmcp.io/owner/repo'
            >>> converter.convert_url("https://gist.github.com/username/gistid")
            'https://gist.gitmcp.io/username/gistid'
        """
        if not url:
            return url

        converted = url

        for pattern, replacement in DOMAIN_MAPPINGS.items():
            converted = re.sub(pattern, replacement, converted, count=1)

        if converted != url:
            logger.debug(f"Converted: {url} → {converted}")
        else:
            logger.debug(f"No conversion needed: {url}")

        return converted

    @staticmethod
    def convert_text(text: str) -> str:
        """
        Convert all GitHub URLs in text to GitMCP format.

        Args:
            text: Text containing GitHub URLs

        Returns:
            Text with converted URLs

        Example:
            >>> text = "Check https://github.com/owner/repo and https://gist.github.com/user/gist123"
            >>> GitMCPURLConverter.convert_text(text)
            'Check https://gitmcp.io/owner/repo and https://gist.gitmcp.io/user/gist123'
        """
        def replacer(match):
            url = match.group(0)
            return GitMCPURLConverter.convert_url(url)

        return URL_PATTERN.sub(replacer, text)

    @staticmethod
    def is_github_url(url: str) -> bool:
        """
        Check if URL is a GitHub URL.

        Args:
            url: URL to check

        Returns:
            True if GitHub URL
        """
        return bool(GITHUB_URL_PATTERN.match(url))

    @staticmethod
    def is_gitmcp_url(url: str) -> bool:
        """
        Check if URL is a GitMCP URL.

        Args:
            url: URL to check

        Returns:
            True if GitMCP URL
        """
        return "gitmcp.io" in url

    @staticmethod
    def extract_repo_from_url(url: str) -> Optional[Tuple[str, str]]:
        """
        Extract owner and repo from GitHub or GitMCP repo URL.

        Args:
            url: Repository URL

        Returns:
            Tuple of (owner, repo) or None if invalid

        Example:
            >>> GitMCPURLConverter.extract_repo_from_url("https://github.com/owner/myrepo")
            ('owner', 'myrepo')
            >>> GitMCPURLConverter.extract_repo_from_url("https://gitmcp.io/owner/myrepo")
            ('owner', 'myrepo')
        """
        # Normalize URL
        url = url.rstrip("/")

        # Match both github and gitmcp URLs
        pattern = r"(?:gitmcp\.io|github\.com)/([^/]+)/([^/]+)(?:/.*)?$"
        match = re.search(pattern, url)

        if match:
            return (match.group(1), match.group(2))

        return None

    @staticmethod
    def extract_gist_from_url(url: str) -> Optional[Tuple[str, str]]:
        """
        Extract username and gist ID from GitHub or GitMCP gist URL.

        Args:
            url: Gist URL

        Returns:
            Tuple of (username, gist_id) or None if invalid

        Example:
            >>> GitMCPURLConverter.extract_gist_from_url("https://gist.github.com/username/gistid123")
            ('username', 'gistid123')
            >>> GitMCPURLConverter.extract_gist_from_url("https://gist.gitmcp.io/username/gistid123")
            ('username', 'gistid123')
        """
        # Normalize URL
        url = url.rstrip("/")

        # Match both github gist and gitmcp gist URLs  
        pattern = r"(?:gist\.gitmcp\.io|gist\.github\.com)/([^/]+)/([^/]+)(?:/.*)?$"
        match = re.search(pattern, url)

        if match:
            return (match.group(1), match.group(2))

        return None

    @staticmethod
    def build_gitmcp_repo_url(owner: str, repo: str, path: str = "") -> str:
        """
        Build a GitMCP repository URL.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Optional path within repo

        Returns:
            Full GitMCP repo URL

        Example:
            >>> GitMCPURLConverter.build_gitmcp_repo_url("owner", "myrepo", "src/main.py")
            'https://gitmcp.io/owner/myrepo/src/main.py'
        """
        url = f"https://gitmcp.io/{owner}/{repo}"
        if path:
            url = f"{url}/{path.lstrip('/')}"
        return url

    @staticmethod
    def build_gitmcp_gist_url(username: str, gist_id: str) -> str:
        """
        Build a GitMCP gist URL.

        Args:
            username: Gist owner username
            gist_id: Gist ID

        Returns:
            Full GitMCP gist URL

        Example:
            >>> GitMCPURLConverter.build_gitmcp_gist_url("username", "gistid123")
            'https://gist.gitmcp.io/username/gistid123'
        """
        return f"https://gist.gitmcp.io/{username}/{gist_id}"

    @staticmethod
    def build_github_gist_url(username: str, gist_id: str) -> str:
        """
        Build a GitHub gist URL.

        Args:
            username: Gist owner username
            gist_id: Gist ID

        Returns:
            Full GitHub gist URL

        Example:
            >>> GitMCPURLConverter.build_github_gist_url("username", "gistid123")
            'https://gist.github.com/username/gistid123'
        """
        return f"https://gist.github.com/{username}/{gist_id}"
