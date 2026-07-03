"""
Integration tests for GitHub Gist MCP support.

Tests:
  - Gist client authentication and rate limiting
  - Public gist fetching
  - Secret gist access (with auth)
  - URL conversion (github.com → gitmcp.io)
  - Pattern extraction from gists
  - Deduplication via SHA256 hash
  - MCP tools integration
  - Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import hashlib

from advancement_machine.intel_mcp.gist_client import (
    GistClient,
    GitHubGist,
    GistFile,
    GistClientError,
    AuthenticationError,
    ResourceNotFoundError,
    RateLimitExceededError,
)
from advancement_machine.intel_mcp.gist_collector import GistCollector
from advancement_machine.intel_mcp.gitmcp_url_converter import GitMCPURLConverter
from advancement_machine.intel_mcp.gist_mcp_tools import GistMCPTools


class TestGistClient:
    """Test GitHub Gist API client."""

    @pytest.fixture
    def client(self):
        """Create test gist client."""
        return GistClient(token="test_token_123")

    def test_client_initialization(self, client):
        """Test client initializes with token."""
        assert client.token == "test_token_123"
        assert client.api_base == "https://api.github.com"
        assert client.rate_limit_remaining >= 0

    def test_client_initialization_without_token(self):
        """Test client initializes without token (public gists only)."""
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            client = GistClient()
            assert client.token is None
            assert client.rate_limit_remaining == 60

    def test_build_headers_with_token(self, client):
        """Test headers include authorization with token."""
        headers = client._build_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test_token_123"
        assert headers["User-Agent"] == "gitmcp-gist-client/1.0.0"

    def test_build_headers_without_token(self):
        """Test headers exclude authorization without token."""
        client = GistClient(token=None)
        headers = client._build_headers()
        assert "Authorization" not in headers

    def test_gist_file_creation(self):
        """Test GistFile creation from API response."""
        data = {
            "filename": "example.py",
            "type": "text/plain",
            "language": "Python",
            "raw_url": "https://gist.github.com/raw/...",
            "size": 1024,
            "content": "print('hello')",
        }
        file = GistFile.from_dict("example.py", data)
        assert file.filename == "example.py"
        assert file.language == "Python"
        assert file.content == "print('hello')"

    def test_gist_creation_from_dict(self):
        """Test GitHubGist creation from API response."""
        gist_data = {
            "id": "abc123",
            "url": "https://api.github.com/gists/abc123",
            "gist_url_web": "https://gist.github.com/abc123",
            "html_url": "https://gist.github.com/abc123",
            "description": "Test gist",
            "public": True,
            "owner": {"login": "testuser"},
            "files": {
                "test.py": {
                    "filename": "test.py",
                    "type": "text/plain",
                    "language": "Python",
                    "raw_url": "https://...",
                    "size": 100,
                }
            },
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "pushed_at": "2024-01-02T00:00:00Z",
            "comments": 5,
        }

        gist = GitHubGist.from_dict(gist_data)
        assert gist.id == "abc123"
        assert gist.description == "Test gist"
        assert gist.public is True
        assert len(gist.files) == 1
        assert "test.py" in gist.files

    def test_gist_content_hash(self):
        """Test SHA256 hash generation for gist content."""
        gist_data = {
            "id": "abc123",
            "url": "https://api.github.com/gists/abc123",
            "html_url": "https://gist.github.com/abc123",
            "description": "Test",
            "public": True,
            "owner": {"login": "user"},
            "files": {
                "test.py": {
                    "filename": "test.py",
                    "type": "text/plain",
                    "language": "Python",
                    "raw_url": "https://...",
                    "size": 100,
                    "content": "x = 1",
                }
            },
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "pushed_at": "2024-01-02T00:00:00Z",
            "comments": 0,
        }

        gist = GitHubGist.from_dict(gist_data)
        content_hash = gist.get_content_hash()
        assert len(content_hash) == 16
        assert isinstance(content_hash, str)

    @pytest.mark.asyncio
    async def test_get_gist_success(self, client):
        """Test successful gist retrieval."""
        with patch.object(client, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "id": "gist123",
                "url": "https://api.github.com/gists/gist123",
                "html_url": "https://gist.github.com/gist123",
                "description": "Sample gist",
                "public": True,
                "owner": {"login": "user123"},
                "files": {},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "pushed_at": "2024-01-02T00:00:00Z",
                "comments": 0,
            }

            gist = await client.get_gist("gist123")
            assert gist.id == "gist123"
            assert gist.description == "Sample gist"
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_gist_not_found(self, client):
        """Test gist retrieval returns 404."""
        with patch.object(client, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = ResourceNotFoundError("Gist not found")

            with pytest.raises(ResourceNotFoundError):
                await client.get_gist("invalid_gist")

    @pytest.mark.asyncio
    async def test_list_user_gists(self, client):
        """Test listing user gists."""
        with patch.object(client, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": "gist1",
                    "description": "Gist 1",
                    "public": True,
                    "owner": {"login": "user"},
                    "html_url": "https://gist.github.com/gist1",
                    "url": "https://api.github.com/gists/gist1",
                    "files": {},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-02T00:00:00Z",
                    "pushed_at": "2024-01-02T00:00:00Z",
                    "comments": 0,
                }
            ]

            gists = await client.list_user_gists(username="user")
            assert len(gists) > 0
            assert gists[0].id == "gist1"

    @pytest.mark.asyncio
    async def test_list_user_gists_requires_auth(self):
        """Test listing authenticated user gists requires token."""
        client = GistClient(token=None)

        with pytest.raises(AuthenticationError):
            await client.list_user_gists(username=None)


class TestGistCollector:
    """Test Gist collector."""

    @pytest.fixture
    def collector(self):
        """Create test collector."""
        mock_client = Mock(spec=GistClient)
        return GistCollector(mock_client)

    @pytest.mark.asyncio
    async def test_collect_from_users(self, collector):
        """Test collecting gists from users."""
        mock_gist = Mock(spec=GitHubGist)
        mock_gist.id = "gist1"
        mock_gist.description = "Test"
        mock_gist.public = True
        mock_gist.owner = {"login": "testuser"}
        mock_gist.html_url = "https://gist.github.com/gist1"
        mock_gist.files = {}
        mock_gist.updated_at = "2024-01-02T00:00:00Z"
        mock_gist.created_at = "2024-01-01T00:00:00Z"
        mock_gist.get_content_hash = Mock(return_value="abc123")

        collector.client.list_user_gists = AsyncMock(return_value=[mock_gist])

        result = await collector.collect_from_users(usernames=["testuser"])
        assert len(result) > 0
        assert result[0]["id"] == "gist1"

    def test_gist_to_dict_conversion(self, collector):
        """Test converting gist to dictionary."""
        mock_gist = Mock(spec=GitHubGist)
        mock_gist.id = "gist123"
        mock_gist.description = "Test description"
        mock_gist.public = True
        mock_gist.owner = {"login": "user123"}
        mock_gist.html_url = "https://gist.github.com/gist123"
        mock_gist.url = "https://api.github.com/gists/gist123"
        mock_gist.comments = 5
        mock_gist.created_at = "2024-01-01T00:00:00Z"
        mock_gist.updated_at = "2024-01-02T00:00:00Z"
        mock_gist.files = {}
        mock_gist.get_content_hash = Mock(return_value="hash123")

        result = collector._gist_to_dict(mock_gist)
        assert result["id"] == "gist123"
        assert result["description"] == "Test description"
        assert result["owner"] == "user123"


class TestGitMCPURLConverter:
    """Test GitMCP URL converter."""

    def test_convert_github_repo_url(self):
        """Test converting github.com repo URL to gitmcp.io."""
        url = "https://github.com/owner/myrepo"
        converted = GitMCPURLConverter.convert_url(url)
        assert converted == "https://gitmcp.io/owner/myrepo"

    def test_convert_github_gist_url(self):
        """Test converting gist.github.com URL to gist.gitmcp.io."""
        url = "https://gist.github.com/username/gistid123"
        converted = GitMCPURLConverter.convert_url(url)
        assert converted == "https://gist.gitmcp.io/username/gistid123"

    def test_convert_github_pages_url(self):
        """Test converting github.io URL to gitmcp.io."""
        url = "https://owner.github.io/project"
        converted = GitMCPURLConverter.convert_url(url)
        assert converted == "https://owner.gitmcp.io/project"

    def test_convert_text_with_multiple_urls(self):
        """Test converting multiple URLs in text."""
        text = (
            "Check https://github.com/owner/repo and "
            "also https://gist.github.com/user/gistid"
        )
        converted = GitMCPURLConverter.convert_text(text)
        assert "gitmcp.io/owner/repo" in converted
        assert "gist.gitmcp.io/user/gistid" in converted

    def test_extract_repo_from_github_url(self):
        """Test extracting owner/repo from GitHub URL."""
        url = "https://github.com/owner/myrepo"
        owner, repo = GitMCPURLConverter.extract_repo_from_url(url)
        assert owner == "owner"
        assert repo == "myrepo"

    def test_extract_repo_from_gitmcp_url(self):
        """Test extracting owner/repo from GitMCP URL."""
        url = "https://gitmcp.io/owner/myrepo"
        owner, repo = GitMCPURLConverter.extract_repo_from_url(url)
        assert owner == "owner"
        assert repo == "myrepo"

    def test_extract_gist_from_github_url(self):
        """Test extracting username/gist_id from GitHub gist URL."""
        url = "https://gist.github.com/username/gistid123"
        username, gist_id = GitMCPURLConverter.extract_gist_from_url(url)
        assert username == "username"
        assert gist_id == "gistid123"

    def test_extract_gist_from_gitmcp_url(self):
        """Test extracting username/gist_id from GitMCP gist URL."""
        url = "https://gist.gitmcp.io/username/gistid123"
        username, gist_id = GitMCPURLConverter.extract_gist_from_url(url)
        assert username == "username"
        assert gist_id == "gistid123"

    def test_build_gitmcp_repo_url(self):
        """Test building GitMCP repo URL."""
        url = GitMCPURLConverter.build_gitmcp_repo_url("owner", "repo", "path/to/file")
        assert url == "https://gitmcp.io/owner/repo/path/to/file"

    def test_build_gitmcp_gist_url(self):
        """Test building GitMCP gist URL."""
        url = GitMCPURLConverter.build_gitmcp_gist_url("username", "gistid")
        assert url == "https://gist.gitmcp.io/username/gistid"

    def test_is_github_url(self):
        """Test GitHub URL detection."""
        assert GitMCPURLConverter.is_github_url("https://github.com/owner/repo")
        assert GitMCPURLConverter.is_github_url("https://gist.github.com/username/gist")
        assert not GitMCPURLConverter.is_github_url("https://example.com")

    def test_is_gitmcp_url(self):
        """Test GitMCP URL detection."""
        assert GitMCPURLConverter.is_gitmcp_url("https://gitmcp.io/owner/repo")
        assert GitMCPURLConverter.is_gitmcp_url("https://gist.gitmcp.io/username/gist")
        assert not GitMCPURLConverter.is_gitmcp_url("https://github.com/owner/repo")


class TestGistMCPTools:
    """Test Gist MCP tools."""

    @pytest.fixture
    def tools(self):
        """Create test tools."""
        return GistMCPTools(github_token="test_token")

    @pytest.mark.asyncio
    async def test_scan_public_gists(self, tools):
        """Test scanning public gists."""
        mock_gist_dict = {
            "id": "gist1",
            "description": "Test gist",
            "owner": "testuser",
            "html_url": "https://gist.github.com/gist1",
            "files": [],
            "content_hash": "hash123",
            "patterns": [],
        }

        with patch.object(tools.collector, "collect_from_users", new_callable=AsyncMock) as mock:
            mock.return_value = [mock_gist_dict]

            result = await tools.scan_public_gists(usernames=["testuser"])
            assert result["status"] == "success"
            assert len(result["gists"]) > 0

    @pytest.mark.asyncio
    async def test_convert_github_url_tool(self, tools):
        """Test URL conversion tool."""
        result = await tools.convert_github_url("https://github.com/owner/repo")
        assert result["status"] == "success"
        assert result["gitmcp_url"] == "https://gitmcp.io/owner/repo"
        assert result["url_type"] == "repository"

    @pytest.mark.asyncio
    async def test_convert_github_gist_url_tool(self, tools):
        """Test gist URL conversion tool."""
        result = await tools.convert_github_url("https://gist.github.com/user/gistid")
        assert result["status"] == "success"
        assert result["gitmcp_url"] == "https://gist.gitmcp.io/user/gistid"
        assert result["url_type"] == "gist"


class TestErrorHandling:
    """Test error handling in Gist client."""

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test authentication error handling."""
        client = GistClient(token="invalid_token")

        with patch.object(client, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = AuthenticationError("Invalid token")

            with pytest.raises(AuthenticationError):
                await client.get_gist("somegist")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test rate limit error handling."""
        client = GistClient(token="test_token")

        with patch.object(client, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RateLimitExceededError("Rate limit exceeded")

            with pytest.raises(RateLimitExceededError):
                await client.get_gist("somegist")


class TestIntegration:
    """Integration tests for full gist MCP workflow."""

    @pytest.mark.asyncio
    async def test_full_gist_workflow(self):
        """Test complete gist fetching and conversion workflow."""
        # Create tools instance
        tools = GistMCPTools(github_token="test_token")

        # Convert URL
        url_result = await tools.convert_github_url("https://gist.github.com/user/gist123")
        assert "gist.gitmcp.io" in url_result["gitmcp_url"]

        # Verify URL extraction
        username, gist_id = GitMCPURLConverter.extract_gist_from_url(url_result["gitmcp_url"])
        assert username == "user"
        assert gist_id == "gist123"

    def test_deduplication_with_hash(self):
        """Test deduplication works via content hash."""
        gist_data = {
            "id": "gist1",
            "url": "https://api.github.com/gists/gist1",
            "html_url": "https://gist.github.com/gist1",
            "description": "Test",
            "public": True,
            "owner": {"login": "user"},
            "files": {
                "file1.py": {
                    "filename": "file1.py",
                    "type": "text/plain",
                    "language": "Python",
                    "raw_url": "https://...",
                    "size": 100,
                    "content": "print('hello')",
                }
            },
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "pushed_at": "2024-01-02T00:00:00Z",
            "comments": 0,
        }

        gist1 = GitHubGist.from_dict(gist_data)
        hash1 = gist1.get_content_hash()

        # Same content, different gist ID
        gist_data["id"] = "gist2"
        gist2 = GitHubGist.from_dict(gist_data)
        hash2 = gist2.get_content_hash()

        # Hashes should match for identical content
        assert hash1 == hash2
