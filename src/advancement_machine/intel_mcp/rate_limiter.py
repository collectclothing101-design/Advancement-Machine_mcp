"""
Rate Limiter - Phase 2

Token bucket rate limiting: per-user/task quotas to prevent abuse and
resource depletion.

Algorithm: Token bucket (standard)
- Capacity: Max tokens per user/task
- Refill rate: Tokens per second
- Each request costs 1 token
- When depleted, requests denied until refill
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional
from collections import defaultdict
import threading
import logging

logger = logging.getLogger("gitmcp.rate_limiter")


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    capacity: int          # Max tokens
    refill_rate: float      # Tokens per second
    tokens: float = 0.0
    last_refill: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        """Initialize tokens to capacity."""
        self.tokens = float(self.capacity)
    
    def allow_request(self) -> bool:
        """
        Check if request is allowed (consume token if so).
        
        Returns:
            True if request allowed, False if rate limited
        """
        self._refill()
        
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        
        return False
    
    def allow_request_amount(self, amount: float = 1.0) -> bool:
        """
        Check if request consuming `amount` tokens is allowed.
        
        Args:
            amount: Number of tokens to consume
        
        Returns:
            True if allowed, False if rate limited
        """
        self._refill()
        
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        
        return False
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_refill).total_seconds()
        
        # Add tokens based on refill rate
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        
        self.last_refill = now
    
    def get_tokens(self) -> float:
        """Get current token count (triggers refill)."""
        self._refill()
        return self.tokens
    
    def reset(self):
        """Reset bucket to capacity."""
        self.tokens = float(self.capacity)
        self.last_refill = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict:
        """Export state."""
        self._refill()
        return {
            "tokens": self.tokens,
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "last_refill": self.last_refill.isoformat()
        }


class RateLimiter:
    """
    Per-user/task rate limiting using token buckets.
    
    Supports different quotas for different users/tasks.
    """
    
    def __init__(
        self,
        default_rps: int = 100,  # Requests per second
        bursts: int = 10,  # Allow bursts at capacity
    ):
        """
        Initialize rate limiter.
        
        Args:
            default_rps: Default requests per second (refill rate)
            bursts: Burst capacity (tokens)
        """
        self.default_rps = default_rps
        self.default_capacity = bursts
        
        # Per-user buckets: {user_id: bucket}
        self.user_buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_rps
            )
        )
        
        # Per-task buckets: {task_name: bucket}
        self.task_buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_rps
            )
        )
        
        # Per-user-task buckets: {(user_id, task_name): bucket}
        self.combined_buckets: Dict[Tuple[str, str], TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=self.default_capacity,
                refill_rate=self.default_rps
            )
        )
        
        # Lock for thread safety
        self.lock = threading.RLock()
    
    def set_user_quota(self, user_id: str, rps: int, burst: int):
        """Set quota for specific user."""
        with self.lock:
            self.user_buckets[user_id] = TokenBucket(
                capacity=burst,
                refill_rate=rps
            )
    
    def set_task_quota(self, task_name: str, rps: int, burst: int):
        """Set quota for specific task."""
        with self.lock:
            self.task_buckets[task_name] = TokenBucket(
                capacity=burst,
                refill_rate=rps
            )
    
    def is_allowed_user(self, user_id: str) -> bool:
        """Check if user is below rate limit."""
        with self.lock:
            return self.user_buckets[user_id].allow_request()
    
    def is_allowed_task(self, task_name: str) -> bool:
        """Check if task is below system rate limit."""
        with self.lock:
            return self.task_buckets[task_name].allow_request()
    
    def is_allowed_combined(
        self,
        user_id: str,
        task_name: str,
        strict: bool = True
    ) -> bool:
        """
        Check if user+task is allowed.
        
        Args:
            user_id: User identifier
            task_name: Task name
            strict: If True, check all three rate limits (user, task, combined)
                   If False, check only combined limit
        
        Returns:
            True if allowed, False if any rate limit exceeded
        """
        with self.lock:
            if strict:
                # Check all three independently
                user_ok = self.user_buckets[user_id].allow_request()
                task_ok = self.task_buckets[task_name].allow_request()
                combined_ok = self.combined_buckets[(user_id, task_name)].allow_request()
                
                if not (user_ok and task_ok and combined_ok):
                    logger.warning(
                        f"Rate limit exceeded for {user_id}:{task_name} "
                        f"(user={user_ok}, task={task_ok}, combined={combined_ok})"
                    )
                    return False
                return True
            else:
                # Check only combined limit
                return self.combined_buckets[(user_id, task_name)].allow_request()
    
    def get_user_status(self, user_id: str) -> Dict:
        """Get rate limit status for user."""
        with self.lock:
            bucket = self.user_buckets[user_id]
            return {
                "user_id": user_id,
                "status": "ok" if bucket.get_tokens() >= 1 else "rate_limited",
                "tokens_remaining": bucket.get_tokens(),
                "capacity": bucket.capacity,
                "refill_rate_rps": bucket.refill_rate
            }
    
    def get_task_status(self, task_name: str) -> Dict:
        """Get rate limit status for task."""
        with self.lock:
            bucket = self.task_buckets[task_name]
            return {
                "task": task_name,
                "status": "ok" if bucket.get_tokens() >= 1 else "rate_limited",
                "tokens_remaining": bucket.get_tokens(),
                "capacity": bucket.capacity,
                "refill_rate_rps": bucket.refill_rate
            }
    
    def get_combined_status(self, user_id: str, task_name: str) -> Dict:
        """Get rate limit status for user+task."""
        with self.lock:
            user_bucket = self.user_buckets[user_id]
            task_bucket = self.task_buckets[task_name]
            combined_bucket = self.combined_buckets[(user_id, task_name)]
            
            return {
                "user_id": user_id,
                "task": task_name,
                "user_tokens": user_bucket.get_tokens(),
                "task_tokens": task_bucket.get_tokens(),
                "combined_tokens": combined_bucket.get_tokens(),
                "status": (
                    "ok" if all([
                        user_bucket.get_tokens() >= 1,
                        task_bucket.get_tokens() >= 1,
                        combined_bucket.get_tokens() >= 1
                    ])
                    else "rate_limited"
                )
            }
    
    def reset_user(self, user_id: str):
        """Reset rate limit for user."""
        with self.lock:
            self.user_buckets[user_id].reset()
    
    def reset_task(self, task_name: str):
        """Reset rate limit for task."""
        with self.lock:
            self.task_buckets[task_name].reset()
    
    def reset_combined(self, user_id: str, task_name: str):
        """Reset rate limit for user+task."""
        with self.lock:
            self.combined_buckets[(user_id, task_name)].reset()
    
    def reset_all(self):
        """Reset all rate limits."""
        with self.lock:
            for bucket in self.user_buckets.values():
                bucket.reset()
            for bucket in self.task_buckets.values():
                bucket.reset()
            for bucket in self.combined_buckets.values():
                bucket.reset()


# Global rate limiter singleton
_GLOBAL_RATE_LIMITER: Optional[RateLimiter] = None


def get_global_limiter() -> RateLimiter:
    """Get or create global rate limiter."""
    global _GLOBAL_RATE_LIMITER
    if _GLOBAL_RATE_LIMITER is None:
        _GLOBAL_RATE_LIMITER = RateLimiter(
            default_rps=100,  # 100 requests/second default
            bursts=10
        )
    return _GLOBAL_RATE_LIMITER
