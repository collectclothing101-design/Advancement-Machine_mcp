"""
GitHub Gists API wrapper module with public and secret gist support.

This module provides a GitHub Gists API client that handles authentication,
public and secret/private gist retrieval, and automatic retries with exponential backoff.

Features:
    - Public gist access (no auth required)
    - Secret/private gist access (auth required with gist scope)
    - File content extraction from gists
    - Gist metadata and description parsing
    - Rate limiting and retry logic
    - Deduplication via SHA256 hash

Example:
    >>> client = GistClient(token="ghp_xxxxx")
    >>> gist = await client.get_gist("gistid123")
    >>> user_gists = await client.list_user_gists(include_secret=True)
"""

import asyncio
import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeVar

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Type variable for generic response types
T = TypeVar("T")

# Constants
MAX_RETRIES = 3
BASE_BACKOFF_MS = 1000
FETCH_TIMEOUT_S = 30
GITHUB_API_VERSION = "2022-11-28"
USER_AGENT = "gitmcp-gist-client/1.0.0"
DEFAULT_API_BASE = "https://api.github.com"
GIST_API_BASE = "https://gist.github.com"

# Create logger
logger = logging.getLogger("gist_client")


@dataclass
class GistFile:
    """Represents a file within a GitHub Gist."""

    filename: str
    type: str  # "text/plain", "application/json", etc.
    language: Optional[str]
    raw_url: str
    size: int
    content: Optional[str] = None

    @classmethod
    def from_dict(cls, filename: str, data: Dict[str, Any]) -> "GistFile":
        """Create GistFile from API dictionary response."""
        return cls(
            filename=filename,
            type=data.get("type", "text/plain"),
            language=data.get("language"),
            raw_url=data.get("raw_url", ""),
            size=data.get("size", 0),
            content=data.get("content"),
        )


@dataclass
class GitHubGist:
    """Represents a GitHub Gist from API response."""

    id: str
    url: str
    gist_url_web: str  # https://gist.github.com/{id}
    forks_url: str
    commits_url: str
    owner: Dict[str, Any]
    description: Optional[str]
    public: bool
    truncated: bool
    comments: int
    created_at: str
    updated_at: str
    pushed_at: str
    html_url: str
    files: Dict[str, GistFile] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GitHubGist":
        """Create GitHubGist from API dictionary response."""
        # Parse files
        files_dict: Dict[str, GistFile] = {}
        for filename, file_data in data.get("files", {}).items():
            files_dict[filename] = GistFile.from_dict(filename, file_data)

        return cls(
            id=data.get("id", ""),
            url=data.get("url", ""),
            gist_url_web=data.get("gist_url_web", ""),
            forks_url=data.get("forks_url", ""),
            commits_url=data.get("commits_url", ""),
            owner=data.get("owner", {}),
            description=data.get("description"),
            public=data.get("public", False),
            truncated=data.get("truncated", False),
            comments=data.get("comments", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            pushed_at=data.get("pushed_at", ""),
            html_url=data.get("html_url", ""),
            files=files_dict,
        )

    def get_content_hash(self) -> str:
        """
        Generate SHA256 hash of gist content for deduplication.

        Returns:
            First 16 characters of SHA256 hash (same as repos)
        """
        combined_content = ""
        for file in sorted(self.files.values(), key=lambda f: f.filename):
            combined_content += f"{file.filename}:{file.content or ''}\n"

        hash_obj = hashlib.sha256(combined_content.encode())
        return hash_obj.hexdigest()[:16]


class GistClientError(Exception):
    """Base exception for Gist client errors."""

    pass


class RateLimitExceededError(GistClientError):
    """Raised when rate limit is exceeded and retries are exhausted."""

    pass


class ResourceNotFoundError(GistClientError):
    """Raised when a requested resource is not found (404)."""

    pass


class AuthenticationError(GistClientError):
    """Raised when authentication fails (401/403)."""

    pass


class GistClient:
    """
    GitHub Gists API wrapper with token authentication, rate limiting, and retry logic.

    Features:
        - Token-based authentication (GitHub Personal Access Token with gist scope)
        - Automatic rate limit tracking (5000 req/hr for authenticated)
        - Exponential backoff retry logic for transient failures
        - Request timeout protection (30 seconds)
        - Comprehensive error handling
        - Public and secret gist support

    Args:
        token: GitHub Personal Access Token with gist scope. If not provided,
               will attempt to load from GITHUB_TOKEN environment variable.
               Falls back to unauthenticated access for public gists only.
        api_base: Base URL for GitHub API (default: https://api.github.com)

    Example:
        >>> client = GistClient(token="ghp_xxxx")
        >>> public_gist = await client.get_gist("gistid123")
        >>> user_gists = await client.list_user_gists(include_secret=True)
        >>> content = await client.get_gist_file_content(gist.files["main.py"])
    """

    def __init__(
        self,
        token: Optional[str] = None,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        """
        Initialize GitHub Gists API client.

        Args:
            token: GitHub Personal Access Token (optional)
            api_base: GitHub API base URL
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.api_base = api_base
        self.rate_limit_remaining = 60
        self.rate_limit_reset = 0
        self._last_request_time = 0.0

        # Create session with retry strategy for connection issues
        self.session = self._create_session()

        if not self.token:
            logger.warning(
                "No GitHub token configured — rate limits will be severely restricted "
                "(60 req/hr instead of 5000 req/hr) and secret gists will be inaccessible"
            )

    def _create_session(self) -> requests.Session:
        """
        Create a requests session with retry strategy for connection failures.

        Returns:
            Configured requests.Session object
        """
        session = requests.Session()

        # Configure retry strategy for connection errors
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _build_headers(self) -> Dict[str, str]:
        """
        Build HTTP headers for GitHub API requests.

        Returns:
            Dictionary of HTTP headers
        """
        headers: Dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": USER_AGENT,
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def _update_rate_limit(self, response: requests.Response) -> None:
        """
        Update internal rate limit tracking from response headers.

        GitHub returns X-RateLimit-* headers in every response.

        Args:
            response: Response object from requests library
        """
        headers = response.headers

        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")

        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        if reset is not None:
            # Convert Unix timestamp (seconds) to milliseconds
            self.rate_limit_reset = int(reset) * 1000

        if self.rate_limit_remaining <= 5:
            reset_dt = datetime.fromtimestamp(
                self.rate_limit_reset / 1000, tz=timezone.utc
            )
            logger.warning(
                f"GitHub rate limit nearly exhausted: {self.rate_limit_remaining} remaining, "
                f"resets at {reset_dt.isoformat()}"
            )

    async def _wait_for_rate_limit(self) -> None:
        """
        Wait if rate limit is exhausted.

        If no requests remain, sleep until the rate limit reset time.
        """
        if self.rate_limit_remaining > 0:
            return

        now_ms = int(time.time() * 1000)
        wait_ms = max(0, self.rate_limit_reset - now_ms + 1000)

        if wait_ms > 0:
            wait_s = wait_ms / 1000
            logger.info(f"Rate limited — waiting {wait_s:.1f}s for reset")
            await asyncio.sleep(wait_s)

    async def _fetch_with_retry(self, url: str, attempt: int = 0) -> Dict[str, Any]:
        """
        Fetch URL with retry logic and rate limit handling.

        Implements exponential backoff for transient errors and rate limiting.
        Retries up to MAX_RETRIES times on connection errors.

        Args:
            url: Full URL to fetch
            attempt: Current attempt number (internal use)

        Returns:
            Parsed JSON response as dictionary

        Raises:
            ResourceNotFoundError: If resource not found (404)
            AuthenticationError: If authentication fails (401/403)
            RateLimitExceededError: If rate limited after max retries
            GistClientError: For other API errors
        """
        await self._wait_for_rate_limit()

        try:
            response = self.session.get(
                url,
                headers=self._build_headers(),
                timeout=FETCH_TIMEOUT_S,
            )

            self._update_rate_limit(response)

            # Handle authentication errors
            if response.status_code == 401:
                raise AuthenticationError("Unauthorized — invalid or missing token")
            if response.status_code == 403:
                # Could be auth or rate limit, check headers
                if response.headers.get("x-ratelimit-remaining") == "0":
                    retry_after = response.headers.get("retry-after")
                    if retry_after:
                        wait_ms = int(retry_after) * 1000
                    else:
                        wait_ms = BASE_BACKOFF_MS * (2 ** attempt)

                    if attempt < MAX_RETRIES:
                        wait_s = wait_ms / 1000
                        logger.warning(
                            f"Rate limited ({response.status_code}), "
                            f"waiting {wait_s:.1f}s before retry"
                        )
                        await asyncio.sleep(wait_s)
                        return await self._fetch_with_retry(url, attempt + 1)
                    else:
                        raise RateLimitExceededError(
                            f"Rate limited after {MAX_RETRIES} retries"
                        )
                else:
                    raise AuthenticationError(
                        "Forbidden — insufficient permissions or authentication failure"
                    )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    wait_ms = int(retry_after) * 1000
                else:
                    wait_ms = BASE_BACKOFF_MS * (2 ** attempt)

                if attempt < MAX_RETRIES:
                    wait_s = wait_ms / 1000
                    logger.warning(
                        f"Rate limited ({response.status_code}), "
                        f"waiting {wait_s:.1f}s before retry"
                    )
                    await asyncio.sleep(wait_s)
                    return await self._fetch_with_retry(url, attempt + 1)
                else:
                    raise RateLimitExceededError(
                        f"Rate limited after {MAX_RETRIES} retries"
                    )

            # Handle not found
            if response.status_code == 404:
                raise ResourceNotFoundError(f"Gist not found: {url}")

            # Handle other HTTP errors
            if not response.ok:
                error_text = response.text[:500] if response.text else "(no response body)"
                raise GistClientError(
                    f"GitHub API error {response.status_code} for {url}: {error_text}"
                )

            try:
                return response.json()
            except ValueError as e:
                raise GistClientError(f"Failed to parse JSON response from {url}: {e}")

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                wait_s = BASE_BACKOFF_MS * (2 ** attempt) / 1000
                logger.warning(
                    f"Request timeout fetching {url}, "
                    f"retry {attempt + 1}/{MAX_RETRIES} after {wait_s:.1f}s"
                )
                await asyncio.sleep(wait_s)
                return await self._fetch_with_retry(url, attempt + 1)
            else:
                raise GistClientError(
                    f"Failed to fetch {url} after {MAX_RETRIES} retries: timeout"
                )

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                wait_s = BASE_BACKOFF_MS * (2 ** attempt) / 1000
                logger.warning(
                    f"Network error fetching {url}, "
                    f"retry {attempt + 1}/{MAX_RETRIES}: {e}"
                )
                await asyncio.sleep(wait_s)
                return await self._fetch_with_retry(url, attempt + 1)
            else:
                raise GistClientError(
                    f"Failed to fetch {url} after {MAX_RETRIES} retries: {e}"
                )

    async def get_gist(self, gist_id: str) -> GitHubGist:
        """
        Get a public or secret gist by ID.

        Requires authentication token if gist is secret/private.

        Args:
            gist_id: GitHub Gist ID

        Returns:
            GitHubGist with metadata and files

        Raises:
            ResourceNotFoundError: If gist not found
            AuthenticationError: If gist is secret and no auth provided
            GistClientError: If the request fails
        """
        url = f"{self.api_base}/gists/{gist_id}"
        logger.debug(f"Fetching gist: {gist_id}")

        data = await self._fetch_with_retry(url)
        gist = GitHubGist.from_dict(data)

        # Attempt to fetch file contents if truncated
        if gist.truncated:
            logger.info(f"Gist {gist_id} is truncated, fetching full files")
            for filename, file in gist.files.items():
                try:
                    content = await self._fetch_file_content(file.raw_url)
                    file.content = content
                except Exception as e:
                    logger.warning(f"Failed to fetch {filename} from {gist_id}: {e}")

        return gist

    async def list_user_gists(
        self, username: Optional[str] = None, include_secret: bool = False
    ) -> List[GitHubGist]:
        """
        List gists for a user or authenticated user.

        Args:
            username: GitHub username. If not provided, lists authenticated user's gists.
            include_secret: If True, include secret/private gists (requires auth)

        Returns:
            List of GitHubGist objects

        Raises:
            AuthenticationError: If trying to list secret gists without auth
            GistClientError: If the request fails
        """
        if username:
            url = f"{self.api_base}/users/{username}/gists"
            logger.debug(f"Fetching public gists for {username}")
        else:
            if not self.token:
                raise AuthenticationError(
                    "Authentication required to list authenticated user's gists"
                )
            url = f"{self.api_base}/user/gists"
            logger.debug("Fetching authenticated user's gists")

        gists: List[GitHubGist] = []
        page = 1

        while True:
            paginated_url = f"{url}?page={page}&per_page=100"
            try:
                data_list = await self._fetch_with_retry(paginated_url)

                if not isinstance(data_list, list) or len(data_list) == 0:
                    break

                for data in data_list:
                    gist = GitHubGist.from_dict(data)

                    # Filter secret gists if not requested
                    if not gist.public and not include_secret:
                        continue

                    gists.append(gist)

                page += 1
            except Exception as e:
                logger.warning(f"Error fetching gists page {page}: {e}")
                break

        logger.info(f"Fetched {len(gists)} gists")
        return gists

    async def _fetch_file_content(self, raw_url: str) -> str:
        """
        Fetch raw file content from raw URL.

        Args:
            raw_url: Raw GitHub URL to file content

        Returns:
            File content as string

        Raises:
            GistClientError: If fetch fails
        """
        try:
            response = self.session.get(raw_url, timeout=FETCH_TIMEOUT_S)
            if not response.ok:
                raise GistClientError(
                    f"Failed to fetch file: {response.status_code}"
                )
            return response.text
        except Exception as e:
            raise GistClientError(f"Failed to fetch file content: {e}")

    async def search_gists(self, query: str) -> List[GitHubGist]:
        """
        Search for public gists by query.

        Args:
            query: Search query string

        Returns:
            List of matching GitHubGist objects

        Raises:
            GistClientError: If the request fails
        """
        # GitHub doesn't have explicit gist search, but we can use code search
        # This is a placeholder for future enhancement
        logger.warning("Gist search is not directly supported via API")
        return []

    async def get_gist_comment_count(self, gist_id: str) -> int:
        """
        Get comment count for a gist.

        Args:
            gist_id: GitHub Gist ID

        Returns:
            Number of comments

        Raises:
            GistClientError: If the request fails
        """
        gist = await self.get_gist(gist_id)
        return gist.comments
