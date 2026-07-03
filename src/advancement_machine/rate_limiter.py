"""
Rate limiting middleware for concurrent agent access control.

Uses token bucket algorithm:
  - Each agent gets a bucket with N tokens
  - Each request consumes 1 token
  - Tokens refill at fixed rate (default: 1 token/100ms = 10 req/sec)
  - When bucket empty, request is rate-limited

Usage:
    from advancement_machine.rate_limiter import RateLimiter, RateLimitTier
    
    limiter = RateLimiter(tier=RateLimitTier.NORMAL)  # 10 req/sec
    
    if limiter.allow_request("agent-123"):
        # Process request
    else:
        # Return 429 Too Many Requests
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import time
import threading
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RateLimitTier(Enum):
    """Rate limit tiers for different request types."""
    HIGH = 100      # 100 req/sec (intensive operations like bulkRecord)
    NORMAL = 10     # 10 req/sec (standard operations like record, query)
    LOW = 1         # 1 req/sec (expensive operations like forecast)


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting using leaky bucket algorithm.
    
    Thread-safe implementation with automatic token refill.
    """
    capacity: int              # Max tokens in bucket
    refill_rate: int          # Tokens per second
    tokens: float = field(default_factory=lambda: 0)
    last_refill: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    def __post_init__(self):
        """Initialize with full capacity."""
        self.tokens = float(self.capacity)
    
    def try_consume(self, tokens: int = 1) -> tuple[bool, float]:
        """
        Try to consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume (default: 1)
            
        Returns:
            Tuple of (success: bool, remaining_tokens: float)
            - success=True: tokens consumed, request allowed
            - success=False: insufficient tokens, request rate-limited
        """
        with self.lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, 
                            self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            # Try to consume
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, self.tokens
            
            return False, self.tokens


class RateLimiter:
    """
    Rate limiter managing per-agent quotas.
    
    Maintains separate token buckets for each agent, enabling
    concurrent independent rate limiting.
    """
    
    def __init__(self, tier: RateLimitTier = RateLimitTier.NORMAL):
        """
        Initialize rate limiter.
        
        Args:
            tier: RateLimitTier enum value (HIGH/NORMAL/LOW)
        """
        self.tier = tier
        self.buckets: Dict[str, TokenBucket] = {}
        self.lock = threading.Lock()
        logger.info(f"RateLimiter initialized: tier={tier.name} ({tier.value} req/sec)")
    
    def get_or_create_bucket(self, agent_id: str) -> TokenBucket:
        """
        Get or create token bucket for agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            TokenBucket for this agent
        """
        with self.lock:
            if agent_id not in self.buckets:
                self.buckets[agent_id] = TokenBucket(
                    capacity=self.tier.value,
                    refill_rate=self.tier.value
                )
                logger.debug(f"Created bucket for agent {agent_id}")
            return self.buckets[agent_id]
    
    def allow_request(self, agent_id: str) -> bool:
        """
        Check if request is allowed for agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            True if request allowed, False if rate-limited
        """
        bucket = self.get_or_create_bucket(agent_id)
        allowed, remaining = bucket.try_consume(1)
        
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for agent {agent_id} "
                f"(remaining: {remaining:.2f} tokens)"
            )
        
        return allowed
    
    def get_status(self, agent_id: str) -> Dict:
        """
        Get current rate limit status for agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            Dict with status: {capacity, refill_rate, tokens, tier}
        """
        bucket = self.get_or_create_bucket(agent_id)
        
        with bucket.lock:
            now = time.time()
            elapsed = now - bucket.last_refill
            current_tokens = min(
                bucket.capacity,
                bucket.tokens + elapsed * bucket.refill_rate
            )
        
        return {
            "capacity": bucket.capacity,
            "refill_rate": bucket.refill_rate,
            "current_tokens": current_tokens,
            "tier": self.tier.name,
            "agent_id": agent_id
        }
    
    def reset_agent(self, agent_id: str) -> None:
        """Reset rate limit for a specific agent."""
        with self.lock:
            if agent_id in self.buckets:
                bucket = self.buckets[agent_id]
                with bucket.lock:
                    bucket.tokens = float(bucket.capacity)
                logger.info(f"Reset rate limit for agent {agent_id}")
    
    def get_agent_count(self) -> int:
        """Get number of agents currently being rate-limited."""
        with self.lock:
            return len(self.buckets)


# Module-level rate limiters for each tier
_limiters = {
    RateLimitTier.HIGH: RateLimiter(RateLimitTier.HIGH),
    RateLimitTier.NORMAL: RateLimiter(RateLimitTier.NORMAL),
    RateLimitTier.LOW: RateLimiter(RateLimitTier.LOW),
}


def get_limiter(tier: RateLimitTier = RateLimitTier.NORMAL) -> RateLimiter:
    """
    Get a rate limiter for the specified tier.
    
    Args:
        tier: RateLimitTier enum value
        
    Returns:
        RateLimiter singleton for that tier
    """
    return _limiters[tier]


def allow_request(agent_id: str, tier: RateLimitTier = RateLimitTier.NORMAL) -> bool:
    """
    Convenience function to check if request is allowed.
    
    Args:
        agent_id: Unique agent identifier
        tier: RateLimitTier for this operation
        
    Returns:
        True if request allowed, False if rate-limited
    """
    limiter = get_limiter(tier)
    return limiter.allow_request(agent_id)
