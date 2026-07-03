"""
GitHub API wrapper module with rate limiting and retry logic.

This module provides a GitHub API client that handles authentication,
rate limiting (5000 req/hr for authenticated requests, 60 req/hr unauthenticated),
and automatic retries with exponential backoff.

Example:
    >>> client = GitHubClient(token="ghp_xxxxx")
    >>> results = await client.search_repos("machine learning", sort="stars", per_page=30)
    >>> repo = await client.get_repo("owner", "repo-name")
"""

import asyncio
import base64
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
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
USER_AGENT = "claude-intel-mcp/1.0.0"
DEFAULT_API_BASE = "https://api.github.com"

# Create logger
logger = logging.getLogger("github_client")


@dataclass
class GithubRepo:
    """Represents a GitHub repository from API response."""

    id: int
    full_name: str
    name: str
    description: Optional[str]
    html_url: str
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    topics: List[str]
    language: Optional[str]
    pushed_at: str
    created_at: str
    updated_at: str
    fork: bool
    archived: bool
    disabled: bool
    license: Optional[Dict[str, str]]
    owner: Dict[str, str]
    default_branch: str
    size: int
    watchers_count: int
    has_issues: bool
    has_wiki: bool
    has_pages: bool
    subscribers_count: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubRepo":
        """Create GithubRepo from API dictionary response."""
        return cls(
            id=data.get("id", 0),
            full_name=data.get("full_name", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            html_url=data.get("html_url", ""),
            stargazers_count=data.get("stargazers_count", 0),
            forks_count=data.get("forks_count", 0),
            open_issues_count=data.get("open_issues_count", 0),
            topics=data.get("topics", []),
            language=data.get("language"),
            pushed_at=data.get("pushed_at", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            fork=data.get("fork", False),
            archived=data.get("archived", False),
            disabled=data.get("disabled", False),
            license=data.get("license"),
            owner=data.get("owner", {}),
            default_branch=data.get("default_branch", "main"),
            size=data.get("size", 0),
            watchers_count=data.get("watchers_count", 0),
            has_issues=data.get("has_issues", False),
            has_wiki=data.get("has_wiki", False),
            has_pages=data.get("has_pages", False),
            subscribers_count=data.get("subscribers_count", 0),
        )


@dataclass
class GithubSearchResult:
    """Represents GitHub search results."""

    total_count: int
    incomplete_results: bool
    items: List[GithubRepo]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubSearchResult":
        """Create GithubSearchResult from API dictionary response."""
        items = [GithubRepo.from_dict(item) for item in data.get("items", [])]
        return cls(
            total_count=data.get("total_count", 0),
            incomplete_results=data.get("incomplete_results", False),
            items=items,
        )


@dataclass
class RateLimit:
    """Represents GitHub API rate limit status."""

    limit: int
    remaining: int
    reset: int
    used: int


@dataclass
class GithubFileContent:
    """Represents GitHub file content response."""

    type: str
    encoding: str
    size: int
    name: str
    path: str
    content: str
    sha: str
    url: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubFileContent":
        """Create GithubFileContent from API dictionary response."""
        return cls(
            type=data.get("type", "file"),
            encoding=data.get("encoding", "utf-8"),
            size=data.get("size", 0),
            name=data.get("name", ""),
            path=data.get("path", ""),
            content=data.get("content", ""),
            sha=data.get("sha", ""),
            url=data.get("url", ""),
        )


@dataclass
class GithubContributor:
    """Represents a GitHub repository contributor."""

    login: str
    contributions: int
    type: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GithubContributor":
        """Create GithubContributor from API dictionary response."""
        return cls(
            login=data.get("login", ""),
            contributions=data.get("contributions", 0),
            type=data.get("type", "User"),
        )


class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""

    pass


class RateLimitExceededError(GitHubClientError):
    """Raised when rate limit is exceeded and retries are exhausted."""

    pass


class ResourceNotFoundError(GitHubClientError):
    """Raised when a requested resource is not found (404)."""

    pass


class GitHubClient:
    """
    GitHub API wrapper with token authentication, rate limiting, and retry logic.

    Features:
        - Token-based authentication (GitHub Personal Access Token)
        - Automatic rate limit tracking (5000 req/hr for authenticated)
        - Exponential backoff retry logic for transient failures
        - Request timeout protection (30 seconds)
        - Comprehensive error handling

    Args:
        token: GitHub Personal Access Token. If not provided, will attempt to
               load from GITHUB_TOKEN environment variable.
        api_base: Base URL for GitHub API (default: https://api.github.com)

    Example:
        >>> client = GitHubClient(token="ghp_xxxx")
        >>> results = await client.search_repos("python machine learning")
        >>> repo_info = await client.get_repo("torvalds", "linux")
    """

    def __init__(
        self,
        token: Optional[str] = None,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        """
        Initialize GitHub API client.

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
                "(60 req/hr instead of 5000 req/hr)"
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
            reset_dt = datetime.fromtimestamp(self.rate_limit_reset / 1000)
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
            RateLimitExceededError: If rate limited after max retries
            GitHubClientError: For other API errors
        """
        await self._wait_for_rate_limit()

        try:
            response = self.session.get(
                url,
                headers=self._build_headers(),
                timeout=FETCH_TIMEOUT_S,
            )

            self._update_rate_limit(response)

            # Handle rate limiting - retry if we haven't exceeded max retries
            if response.status_code in (429, 403):
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
                raise ResourceNotFoundError(f"Resource not found: {url}")

            # Handle other HTTP errors
            if not response.ok:
                error_text = response.text[:500] if response.text else "(no response body)"
                raise GitHubClientError(
                    f"GitHub API error {response.status_code} for {url}: {error_text}"
                )

            try:
                return response.json()
            except ValueError as e:
                raise GitHubClientError(f"Failed to parse JSON response from {url}: {e}")

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
                raise GitHubClientError(
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
                raise GitHubClientError(
                    f"Failed to fetch {url} after {MAX_RETRIES} retries: {e}"
                )

    async def search_repos(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 30,
    ) -> GithubSearchResult:
        """
        Search for repositories on GitHub.

        Args:
            query: Search query string (e.g., "language:python stars:>1000")
            sort: Sort order - "stars", "forks", "updated", or "best-match"
            order: Sort direction - "asc" or "desc"
            per_page: Results per page (max 100)

        Returns:
            GithubSearchResult with total count and matching repositories

        Raises:
            GitHubClientError: If the search request fails
        """
        # Validate and cap per_page
        per_page = min(per_page, 100)

        # Build query parameters
        params = {
            "q": query,
            "order": order,
            "per_page": str(per_page),
        }

        # Don't include sort for "best-match" (GitHub default)
        if sort != "best-match":
            params["sort"] = sort

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.api_base}/search/repositories?{query_string}"

        logger.debug(f"Searching repos: query={query}, sort={sort}, per_page={per_page}")

        data = await self._fetch_with_retry(url)
        return GithubSearchResult.from_dict(data)

    async def get_repo(self, owner: str, repo: str) -> GithubRepo:
        """
        Get detailed information about a specific repository.

        Args:
            owner: Repository owner login
            repo: Repository name

        Returns:
            GithubRepo with complete repository metadata

        Raises:
            ResourceNotFoundError: If repository not found
            GitHubClientError: If the request fails
        """
        url = f"{self.api_base}/repos/{owner}/{repo}"
        data = await self._fetch_with_retry(url)
        return GithubRepo.from_dict(data)

    async def get_readme(self, owner: str, repo: str) -> str:
        """
        Fetch README.md content from a repository.

        Automatically decodes base64-encoded responses from the API.

        Args:
            owner: Repository owner login
            repo: Repository name

        Returns:
            README content as string, or empty string if not found

        Raises:
            GitHubClientError: For unexpected errors (not 404)
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/readme"
            data = await self._fetch_with_retry(url)

            file_content = GithubFileContent.from_dict(data)

            # Decode base64 if needed
            if file_content.encoding == "base64":
                content_bytes = file_content.content.replace("\n", "")
                return base64.b64decode(content_bytes).decode("utf-8")

            return file_content.content

        except ResourceNotFoundError:
            logger.debug(f"README not found for {owner}/{repo}")
            return ""

    async def get_file_contents(self, owner: str, repo: str, path: str) -> str:
        """
        Fetch file contents from a repository.

        Automatically decodes base64-encoded responses from the API.

        Args:
            owner: Repository owner login
            repo: Repository name
            path: Path to file in repository

        Returns:
            File content as string, or empty string if not found

        Raises:
            GitHubClientError: For unexpected errors (not 404)
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/contents/{path}"
            data = await self._fetch_with_retry(url)

            file_content = GithubFileContent.from_dict(data)

            # Decode base64 if needed
            if file_content.encoding == "base64":
                content_bytes = file_content.content.replace("\n", "")
                return base64.b64decode(content_bytes).decode("utf-8")

            return file_content.content

        except ResourceNotFoundError:
            logger.debug(f"File not found: {owner}/{repo}/{path}")
            return ""

    async def get_topics(self, owner: str, repo: str) -> List[str]:
        """
        Get topics assigned to a repository.

        Args:
            owner: Repository owner login
            repo: Repository name

        Returns:
            List of topic strings, or empty list if error occurs
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/topics"
            # Required header for topics endpoint
            headers = self._build_headers()
            headers["Accept"] = "application/vnd.github.mercy-preview+json"

            response = self.session.get(
                url,
                headers=headers,
                timeout=FETCH_TIMEOUT_S,
            )

            self._update_rate_limit(response)

            if response.ok:
                data = response.json()
                return data.get("names", [])

            return []

        except Exception as e:
            logger.debug(f"Failed to get topics for {owner}/{repo}: {e}")
            return []

    async def get_contributors(self, owner: str, repo: str) -> List[GithubContributor]:
        """
        Get list of contributors to a repository.

        Args:
            owner: Repository owner login
            repo: Repository name

        Returns:
            List of top contributors (up to 30), or empty list on error
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/contributors?per_page=30"
            data = await self._fetch_with_retry(url)

            # Response is a list of contributors
            if isinstance(data, list):
                return [GithubContributor.from_dict(item) for item in data]

            return []

        except Exception as e:
            logger.debug(f"Failed to get contributors for {owner}/{repo}: {e}")
            return []

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Dictionary with 'remaining' (int) and 'reset_at' (datetime) keys
        """
        reset_dt = datetime.fromtimestamp(self.rate_limit_reset / 1000)
        return {
            "remaining": self.rate_limit_remaining,
            "reset_at": reset_dt,
        }

    def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            self.session.close()

    def __enter__(self) -> "GitHubClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()


class GitHubClientSync:
    """
    Synchronous wrapper around GitHubClient for code that doesn't use async.

    This is a convenience wrapper that runs async methods in an event loop.
    For new code, use GitHubClient directly with async/await.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        """Initialize synchronous wrapper."""
        self.client = GitHubClient(token=token, api_base=api_base)

    def search_repos(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 30,
    ) -> GithubSearchResult:
        """Search for repositories (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.client.search_repos(query, sort, order, per_page)
            )
        finally:
            loop.close()

    def get_repo(self, owner: str, repo: str) -> GithubRepo:
        """Get repository details (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.client.get_repo(owner, repo))
        finally:
            loop.close()

    def get_readme(self, owner: str, repo: str) -> str:
        """Fetch README content (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.client.get_readme(owner, repo))
        finally:
            loop.close()

    def get_file_contents(self, owner: str, repo: str, path: str) -> str:
        """Fetch file contents (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.client.get_file_contents(owner, repo, path))
        finally:
            loop.close()

    def get_topics(self, owner: str, repo: str) -> List[str]:
        """Get topics (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.client.get_topics(owner, repo))
        finally:
            loop.close()

    def get_contributors(self, owner: str, repo: str) -> List[GithubContributor]:
        """Get contributors (sync wrapper)."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.client.get_contributors(owner, repo))
        finally:
            loop.close()

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Get rate limit info."""
        return self.client.get_rate_limit_info()

    def close(self) -> None:
        """Close client."""
        self.client.close()

    def __enter__(self) -> "GitHubClientSync":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
