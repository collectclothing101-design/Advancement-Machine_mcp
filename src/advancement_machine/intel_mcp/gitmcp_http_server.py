"""
GitMCP HTTP API Server: RESTful endpoints for Gist MCP.

Endpoints:
  GET /api/gitmcp/v1/gists/{gist_id}          - Get a gist
  GET /api/gitmcp/v1/users/{username}/gists   - List user's gists
  GET /api/gitmcp/v1/gists/{gist_id}/patterns - Extract patterns
  POST /api/gitmcp/v1/convert-url             - Convert GitHub URL to GitMCP format
  GET /api/gitmcp/v1/suggestions              - Generate gist suggestions
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class HTTPResponse:
    """Simple HTTP response wrapper."""

    def __init__(self, status: int, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        self.status = status
        self.body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            "status": self.status,
            "headers": self.headers,
            "body": self.body,
        }

    def to_json(self) -> str:
        """Convert response to JSON string."""
        return json.dumps({"status": self.status, "headers": self.headers, "body": self.body})


class GitMCPHTTPServer(ABC):
    """Abstract HTTP server interface for GitMCP."""

    def __init__(self, gist_mcp_tools):
        """Initialize HTTP server with tools."""
        self.tools = gist_mcp_tools
        logger.info("GitMCPHTTPServer initialized")

    # ═════════════════════════════════════════════════════════════════════════
    # ENDPOINTS
    # ═════════════════════════════════════════════════════════════════════════

    async def handle_get_gist(self, gist_id: str) -> HTTPResponse:
        """
        GET /api/gitmcp/v1/gists/{gist_id}

        Get a specific gist by ID.

        Query params:
          - include_content: bool (fetch full file content)

        Returns:
            200: Gist metadata and files
            404: Gist not found
            500: Server error
        """
        try:
            logger.debug(f"Fetching gist: {gist_id}")

            gist = await self.tools.gist_client.get_gist(gist_id)

            response_body = {
                "id": gist.id,
                "description": gist.description,
                "url": gist.html_url,
                "gitmcp_url": self.tools.url_converter.build_gitmcp_gist_url(
                    gist.owner.get("login", ""), gist_id
                ),
                "owner": gist.owner.get("login", ""),
                "public": gist.public,
                "comments": gist.comments,
                "created_at": gist.created_at,
                "updated_at": gist.updated_at,
                "files": [
                    {
                        "filename": f.filename,
                        "language": f.language,
                        "size": f.size,
                        "raw_url": f.raw_url,
                    }
                    for f in gist.files.values()
                ],
            }

            return HTTPResponse(200, response_body)

        except Exception as e:
            logger.error(f"Get gist failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    async def handle_list_user_gists(self, username: Optional[str] = None) -> HTTPResponse:
        """
        GET /api/gitmcp/v1/users/{username}/gists
        GET /api/gitmcp/v1/user/gists (authenticated user)

        List gists for a user.

        Query params:
          - include_secret: bool (requires auth)
          - per_page: int (default: 30)

        Returns:
            200: List of gists
            401: Authentication required
            500: Server error
        """
        try:
            logger.debug(f"Listing gists for user: {username or 'authenticated'}")

            gists = await self.tools.collector.collect_from_users(
                usernames=[username] if username else None
            )

            response_body = {
                "username": username or "authenticated_user",
                "gists_count": len(gists),
                "gists": [
                    {
                        "id": g["id"],
                        "description": g.get("description", ""),
                        "owner": g.get("owner", ""),
                        "url": g["html_url"],
                        "gitmcp_url": g.get("gitmcp_url", ""),
                        "public": g.get("public", True),
                        "files_count": len(g.get("files", [])),
                        "updated_at": g.get("updated_at", ""),
                    }
                    for g in gists
                ],
            }

            return HTTPResponse(200, response_body)

        except Exception as e:
            logger.error(f"List user gists failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    async def handle_extract_patterns(self, gist_id: str) -> HTTPResponse:
        """
        GET /api/gitmcp/v1/gists/{gist_id}/patterns

        Extract code patterns from a gist.

        Returns:
            200: Extracted patterns
            404: Gist not found
            500: Server error
        """
        try:
            logger.debug(f"Extracting patterns from gist: {gist_id}")

            result = await self.tools.extract_gist_patterns(gist_id)

            if result["status"] == "error":
                return HTTPResponse(500, result)

            return HTTPResponse(200, result)

        except Exception as e:
            logger.error(f"Extract patterns failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    async def handle_convert_url(self, request_body: Dict[str, Any]) -> HTTPResponse:
        """
        POST /api/gitmcp/v1/convert-url

        Convert GitHub URL to GitMCP format.

        Request body:
        {
            "url": "https://github.com/owner/repo"
        }

        Returns:
            200: Conversion result
            400: Invalid request
            500: Server error
        """
        try:
            url = request_body.get("url", "").strip()

            if not url:
                return HTTPResponse(400, {"error": "Missing 'url' field"})

            result = await self.tools.convert_github_url(url)

            return HTTPResponse(200, result)

        except Exception as e:
            logger.error(f"Convert URL failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    async def handle_suggestions(self) -> HTTPResponse:
        """
        GET /api/gitmcp/v1/suggestions

        Generate gist suggestions.

        Query params:
          - max_suggestions: int (default: 10)

        Returns:
            200: Suggestions list
            500: Server error
        """
        try:
            logger.debug("Generating gist suggestions")

            result = await self.tools.generate_gist_suggestions()

            if result["status"] == "error":
                return HTTPResponse(500, result)

            return HTTPResponse(200, result)

        except Exception as e:
            logger.error(f"Generate suggestions failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    async def handle_scan_gists(
        self, usernames: Optional[list] = None, max_gists: int = 50
    ) -> HTTPResponse:
        """
        GET /api/gitmcp/v1/scan

        Scan and analyze gists.

        Query params:
          - users: comma-separated usernames
          - max_gists: int (default: 50)

        Returns:
            200: Scanned gists
            500: Server error
        """
        try:
            logger.debug(f"Scanning gists from: {usernames or 'default'}")

            result = await self.tools.scan_public_gists(
                usernames=usernames, max_gists=max_gists
            )

            if result["status"] == "error":
                return HTTPResponse(500, result)

            return HTTPResponse(200, result)

        except Exception as e:
            logger.error(f"Scan gists failed: {e}")
            return HTTPResponse(500, {"error": str(e)})

    # ═════════════════════════════════════════════════════════════════════════
    # ROUTING
    # ═════════════════════════════════════════════════════════════════════════

    async def route_request(
        self, method: str, path: str, query_params: Dict[str, Any], body: Optional[Dict[str, Any]] = None
    ) -> HTTPResponse:
        """
        Route HTTP request to appropriate handler.

        Args:
            method: HTTP method (GET, POST)
            path: Request path (e.g., /api/gitmcp/v1/gists/123)
            query_params: Query string parameters
            body: Request body (for POST)

        Returns:
            HTTPResponse
        """
        logger.debug(f"{method} {path}")

        # Remove leading/trailing slashes and split path
        path_parts = [p for p in path.strip("/").split("/") if p]

        try:
            # GET /api/gitmcp/v1/gists/{gist_id}
            if method == "GET" and len(path_parts) >= 5:
                if path_parts[0:4] == ["api", "gitmcp", "v1", "gists"]:
                    gist_id = path_parts[4]

                    # GET /api/gitmcp/v1/gists/{gist_id}/patterns
                    if len(path_parts) > 5 and path_parts[5] == "patterns":
                        return await self.handle_extract_patterns(gist_id)

                    # GET /api/gitmcp/v1/gists/{gist_id}
                    return await self.handle_get_gist(gist_id)

            # GET /api/gitmcp/v1/users/{username}/gists
            if method == "GET" and len(path_parts) >= 5:
                if (
                    path_parts[0:4] == ["api", "gitmcp", "v1", "users"]
                    and path_parts[-1] == "gists"
                ):
                    username = path_parts[4]
                    return await self.handle_list_user_gists(username)

            # GET /api/gitmcp/v1/user/gists (authenticated user)
            if method == "GET" and path_parts[0:4] == ["api", "gitmcp", "v1", "user", "gists"]:
                return await self.handle_list_user_gists(None)

            # POST /api/gitmcp/v1/convert-url
            if method == "POST" and path_parts[0:4] == ["api", "gitmcp", "v1", "convert-url"]:
                return await self.handle_convert_url(body or {})

            # GET /api/gitmcp/v1/suggestions
            if method == "GET" and path_parts[0:4] == ["api", "gitmcp", "v1", "suggestions"]:
                return await self.handle_suggestions()

            # GET /api/gitmcp/v1/scan
            if method == "GET" and path_parts[0:4] == ["api", "gitmcp", "v1", "scan"]:
                usernames = query_params.get("users", "").split(",") if query_params.get("users") else None
                max_gists = int(query_params.get("max_gists", 50))
                return await self.handle_scan_gists(usernames, max_gists)

            # 404 Not Found
            return HTTPResponse(
                404,
                {
                    "error": "Endpoint not found",
                    "path": path,
                    "method": method,
                },
            )

        except Exception as e:
            logger.error(f"Route request error: {e}", exc_info=True)
            return HTTPResponse(500, {"error": "Internal server error"})


class SimpleHTTPServer(GitMCPHTTPServer):
    """Simple HTTP server implementation (testing/reference)."""

    def start(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Start the HTTP server (reference implementation)."""
        logger.info(f"Starting GitMCP HTTP server on {host}:{port}")
        logger.info("This is a routing interface. Use with your preferred ASGI/WSGI framework.")
        logger.info("Supported endpoints:")
        logger.info("  GET  /api/gitmcp/v1/gists/{gist_id}")
        logger.info("  GET  /api/gitmcp/v1/gists/{gist_id}/patterns")
        logger.info("  GET  /api/gitmcp/v1/users/{username}/gists")
        logger.info("  GET  /api/gitmcp/v1/scan")
        logger.info("  POST /api/gitmcp/v1/convert-url")
        logger.info("  GET  /api/gitmcp/v1/suggestions")
