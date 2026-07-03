"""
GitMCP Gist Task Handlers: Atomic, reusable task functions.

This module decompose the Gist client and collector into atomic tasks:
  1. fetch_gist_raw          -> I/O: Fetch raw gist from API
  2. parse_gist_content      -> Pure: Parse content and metadata
  3. dedupe_gist             -> Pure: Check against pattern memory
  4. score_gist              -> Pure: Score by relevance/recency
  5. list_user_gists_raw     -> I/O: List user's gists
  6. extract_patterns_from_gist -> Pure: Extract code patterns

Each task:
  - Has single responsibility
  - Is testable in isolation
  - Produces TaskResult with status + metadata
  - Integrates with TaskContext for metrics/logging
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .task_framework import (
    TaskContext,
    TaskResult,
    TaskStatus,
    task_handler,
    TaskError,
    TaskValidationError,
    TaskAuthError,
    TaskNotFoundError,
)
from .gist_client import GistClient, GitHubGist, GistClientError
from .pattern_memory import PatternMemory

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Raw I/O Tasks (Network operations)
# ═════════════════════════════════════════════════════════════════════════

@task_handler(name="gist:fetch_raw")
async def fetch_gist_raw(context: TaskContext, gist_id: str) -> TaskResult:
    """
    Fetch raw gist data from GitHub API.
    
    Args:
        context: TaskContext with gist_client in state
        gist_id: GitHub gist ID
    
    Returns:
        TaskResult with GitHubGist data
    """
    if not gist_id or not isinstance(gist_id, str):
        raise TaskValidationError(
            f"Invalid gist_id: {gist_id}",
            details={"gist_id": gist_id, "type": type(gist_id).__name__}
        )

    try:
        gist_client: GistClient = context.state.get("gist_client")
        if not gist_client:
            raise TaskAuthError("gist_client not provided in context.state")

        context.log_debug(f"Fetching gist {gist_id} from API")
        gist = await gist_client.get_gist(gist_id)
        context.metrics.inc("gist.fetch.success")
        
        context.log_info(f"Fetched gist {gist_id}: {len(gist.files)} files")
        return TaskResult.success(
            gist,
            metadata={
                "gist_id": gist_id,
                "file_count": len(gist.files),
                "is_public": gist.public,
            }
        )
    except GistClientError as e:
        context.metrics.inc("gist.fetch.error")
        context.log_error(f"GistClientError fetching {gist_id}: {e}")
        raise TaskError(f"Failed to fetch gist {gist_id}: {str(e)}")
    except Exception as e:
        context.metrics.inc("gist.fetch.error")
        context.log_error(f"Unexpected error fetching {gist_id}: {e}")
        raise


@task_handler(name="gist:list_user_raw")
async def list_user_gists_raw(
    context: TaskContext,
    username: Optional[str] = None,
    include_secret: bool = False,
) -> TaskResult:
    """
    List gists for a user.
    
    Args:
        context: TaskContext with gist_client in state
        username: GitHub username (None = authenticated user)
        include_secret: Include private/secret gists
    
    Returns:
        TaskResult with list of GitHubGist objects
    """
    try:
        gist_client: GistClient = context.state.get("gist_client")
        if not gist_client:
            raise TaskAuthError("gist_client not provided in context.state")

        context.log_debug(
            f"Listing gists for username={username}, include_secret={include_secret}"
        )
        gists = await gist_client.list_user_gists(
            username=username,
            include_secret=include_secret,
        )
        context.metrics.inc("gist.list.success")
        
        context.log_info(f"Listed {len(gists)} gists for {username or 'authenticated user'}")
        return TaskResult.success(
            gists,
            metadata={
                "username": username or "authenticated",
                "count": len(gists),
                "include_secret": include_secret,
            }
        )
    except GistClientError as e:
        context.metrics.inc("gist.list.error")
        context.log_error(f"GistClientError listing gists: {e}")
        raise TaskError(f"Failed to list gists: {str(e)}")
    except Exception as e:
        context.metrics.inc("gist.list.error")
        context.log_error(f"Unexpected error listing gists: {e}")
        raise


# ═════════════════════════════════════════════════════════════════════════
# Pure Transformation Tasks (No I/O)
# ═════════════════════════════════════════════════════════════════════════

@task_handler(name="gist:parse_content")
async def parse_gist_content(context: TaskContext, data: GitHubGist) -> TaskResult:
    """
    Parse raw gist data into structured format.
    
    Args:
        context: TaskContext
        data: GitHubGist object
    
    Returns:
        TaskResult with parsed dict
    """
    if not isinstance(data, GitHubGist):
        raise TaskValidationError(
            f"Expected GitHubGist, got {type(data).__name__}",
            details={"received_type": type(data).__name__}
        )

    try:
        file_list = []
        for filename, file_obj in data.files.items():
            file_list.append({
                "filename": filename,
                "type": file_obj.type,
                "language": file_obj.language,
                "size": file_obj.size,
                "raw_url": file_obj.raw_url,
                "content": file_obj.content,
            })

        parsed = {
            "id": data.id,
            "url": data.url,
            "html_url": data.html_url,
            "owner": data.owner.get("login", "") if data.owner else "",
            "description": data.description or "",
            "public": data.public,
            "comments": data.comments,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "files": file_list,
            "file_count": len(data.files),
            "content_hash": data.get_content_hash(),
        }
        context.metrics.inc("gist.parse.success")
        context.log_debug(f"Parsed gist {data.id}: {len(file_list)} files")
        
        return TaskResult.success(
            parsed,
            metadata={
                "gist_id": data.id,
                "file_count": len(file_list),
            }
        )
    except Exception as e:
        context.metrics.inc("gist.parse.error")
        context.log_error(f"Error parsing gist: {e}")
        raise TaskError(f"Failed to parse gist: {str(e)}")


@task_handler(name="gist:extend_with_patterns")
async def extract_patterns_from_gist(
    context: TaskContext,
    data: Dict[str, Any],
) -> TaskResult:
    """
    Extract code patterns from gist content.
    
    Args:
        context: TaskContext with pattern_extractor in state
        data: Parsed gist dict
    
    Returns:
        TaskResult with data + extracted patterns
    """
    if not isinstance(data, dict) or "id" not in data:
        raise TaskValidationError(
            "Expected parsed gist dict with 'id'",
            details={"keys": list(data.keys()) if isinstance(data, dict) else []}
        )

    try:
        pattern_extractor = context.state.get("pattern_extractor")
        if not pattern_extractor:
            # If no extractor available, just return data as-is
            context.log_debug("No pattern_extractor in context; returning data unchanged")
            data["patterns"] = []
            return TaskResult.success(data)

        # Extract patterns from each file's content
        patterns = []
        for file_obj in data.get("files", []):
            if file_obj.get("content"):
                file_patterns = pattern_extractor.extract_patterns(
                    file_obj["content"],
                    language=file_obj.get("language"),
                )
                patterns.extend(file_patterns)

        data["patterns"] = patterns
        context.metrics.inc("gist.extract_patterns.success")
        context.log_info(f"Extracted {len(patterns)} patterns from gist {data['id']}")
        
        return TaskResult.success(
            data,
            metadata={
                "gist_id": data["id"],
                "pattern_count": len(patterns),
            }
        )
    except Exception as e:
        context.metrics.inc("gist.extract_patterns.error")
        context.log_error(f"Error extracting patterns: {e}")
        # Non-fatal: continue without patterns
        data["patterns"] = []
        return TaskResult.success(data)


@task_handler(name="gist:dedupe")
async def dedupe_gist(context: TaskContext, data: Dict[str, Any]) -> TaskResult:
    """
    Check gist against pattern memory for deduplication.
    
    Args:
        context: TaskContext with pattern_memory in state
        data: Parsed gist dict with content_hash
    
    Returns:
        TaskResult with gist + dedup metadata
    """
    if not isinstance(data, dict) or "id" not in data:
        raise TaskValidationError(
            "Expected parsed gist dict with 'id'",
            details={"keys": list(data.keys()) if isinstance(data, dict) else []}
        )

    try:
        pattern_memory: Optional[PatternMemory] = context.state.get("pattern_memory")
        content_hash = data.get("content_hash", "")
        
        if not pattern_memory or not content_hash:
            # If no pattern_memory, assume not deduplicated
            data["is_duplicate"] = False
            data["duplicate_score"] = 0.0
            return TaskResult.success(data)

        # Check if this hash is already in memory (dedup)
        is_duplicate = pattern_memory.check_dedup(content_hash)
        data["is_duplicate"] = is_duplicate
        data["duplicate_score"] = 1.0 if is_duplicate else 0.0
        
        context.metrics.inc(
            "gist.dedupe.duplicate" if is_duplicate else "gist.dedupe.unique"
        )
        context.log_debug(
            f"Gist {data['id']}: is_duplicate={is_duplicate}"
        )
        
        return TaskResult.success(
            data,
            metadata={
                "gist_id": data["id"],
                "content_hash": content_hash,
                "is_duplicate": is_duplicate,
            }
        )
    except Exception as e:
        context.metrics.inc("gist.dedupe.error")
        context.log_error(f"Error deduplicating gist: {e}")
        # Non-fatal: continue without dedup check
        data["is_duplicate"] = False
        data["duplicate_score"] = 0.0
        return TaskResult.success(data)


@task_handler(name="gist:score")
async def score_gist(context: TaskContext, data: Dict[str, Any]) -> TaskResult:
    """
    Score gist by relevance and recency.
    
    Args:
        context: TaskContext
        data: Parsed gist dict
    
    Returns:
        TaskResult with gist + relevance_score
    """
    if not isinstance(data, dict) or "id" not in data:
        raise TaskValidationError(
            "Expected parsed gist dict with 'id'",
            details={"keys": list(data.keys()) if isinstance(data, dict) else []}
        )

    try:
        relevance_scorer = context.state.get("relevance_scorer")
        
        # Base scoring factors
        is_public = data.get("public", False)
        is_duplicate = data.get("is_duplicate", False)
        pattern_count = len(data.get("patterns", []))
        
        # Recency score (0.0 to 1.0, newer = higher)
        now = datetime.now(timezone.utc)
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                updated_at = now
        
        days_old = (now - updated_at).days if updated_at else 0
        recency_score = max(0.0, 1.0 - (days_old / 365.0))  # Decay over 1 year
        
        # Composite score
        score = (
            (0.3 * (1.0 if is_public else 0.5)) +  # Public gist boost
            (0.3 * recency_score) +  # Recency
            (0.2 * min(1.0, pattern_count / 10.0)) +  # Pattern count (max 10 patterns)
            (0.2 * (0.0 if is_duplicate else 1.0))  # Penalize duplicates
        )
        
        if relevance_scorer and hasattr(relevance_scorer, "score"):
            try:
                # If custom scorer available, use it
                custom_score = relevance_scorer.score(data)
                score = 0.6 * score + 0.4 * custom_score
            except Exception as e:
                context.log_debug(f"Custom scorer failed: {e}; using default score")
        
        data["relevance_score"] = score
        context.metrics.inc("gist.score.success")
        context.log_debug(f"Gist {data['id']} scored {score:.3f}")
        
        return TaskResult.success(
            data,
            metadata={
                "gist_id": data["id"],
                "relevance_score": score,
                "recency_score": recency_score,
            }
        )
    except Exception as e:
        context.metrics.inc("gist.score.error")
        context.log_error(f"Error scoring gist: {e}")
        # Non-fatal: default score
        data["relevance_score"] = 0.5
        return TaskResult.success(data)


@task_handler(name="gist:filter_by_threshold")
async def filter_gist_by_score(
    context: TaskContext,
    data: Dict[str, Any],
    min_score: float = 0.3,
) -> TaskResult:
    """
    Filter gist based on relevance score threshold.
    
    Args:
        context: TaskContext
        data: Scored gist dict
        min_score: Minimum relevance score to keep
    
    Returns:
        TaskResult with gist (or error if filtered out)
    """
    try:
        score = data.get("relevance_score", 0.0)
        
        if score < min_score:
            context.metrics.inc("gist.filter.filtered_out")
            context.log_debug(
                f"Gist {data['id']} filtered out (score {score:.3f} < {min_score})"
            )
            return TaskResult(
                data=None,
                status=TaskStatus.SKIPPED,
                metadata={
                    "gist_id": data["id"],
                    "relevance_score": score,
                    "reason": f"score below threshold {min_score}",
                }
            )
        
        context.metrics.inc("gist.filter.passed")
        context.log_debug(f"Gist {data['id']} passed filter (score {score:.3f})")
        
        return TaskResult.success(data)
    except Exception as e:
        context.metrics.inc("gist.filter.error")
        context.log_error(f"Error filtering gist: {e}")
        raise TaskError(f"Failed to filter gist: {str(e)}")


# ═════════════════════════════════════════════════════════════════════════
# Aggregation Tasks (Multiple inputs)
# ═════════════════════════════════════════════════════════════════════════

@task_handler(name="gist:aggregate_list")
async def aggregate_gist_list(
    context: TaskContext,
    gists: list,
    sort_by: str = "relevance_score",
    ascending: bool = False,
) -> TaskResult:
    """
    Aggregate and sort list of gists.
    
    Args:
        context: TaskContext
        gists: List of gist dicts
        sort_by: Field to sort by
        ascending: Sort ascending (default: descending)
    
    Returns:
        TaskResult with sorted list
    """
    try:
        if not isinstance(gists, list):
            raise TaskValidationError(
                f"Expected list of gists, got {type(gists).__name__}"
            )
        
        # Filter out None/skipped items
        valid_gists = [g for g in gists if g is not None]
        
        # Sort
        try:
            sorted_gists = sorted(
                valid_gists,
                key=lambda g: g.get(sort_by, 0),
                reverse=not ascending,
            )
        except (TypeError, KeyError) as e:
            context.log_error(f"Sort error: {e}; returning unsorted")
            sorted_gists = valid_gists
        
        context.metrics.inc("gist.aggregate.success")
        context.log_info(f"Aggregated {len(sorted_gists)} gists, sorted by {sort_by}")
        
        return TaskResult.success(
            sorted_gists,
            metadata={
                "count": len(sorted_gists),
                "sorted_by": sort_by,
                "ascending": ascending,
            }
        )
    except Exception as e:
        context.metrics.inc("gist.aggregate.error")
        context.log_error(f"Error aggregating gists: {e}")
        raise TaskError(f"Failed to aggregate gists: {str(e)}")


__all__ = [
    "fetch_gist_raw",
    "list_user_gists_raw",
    "parse_gist_content",
    "extract_patterns_from_gist",
    "dedupe_gist",
    "score_gist",
    "filter_gist_by_score",
    "aggregate_gist_list",
]
