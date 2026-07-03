from resolver import Resolver
from typing import Dict, Any

class ResolverFactory:
    """Creates resolver instances with shared config."""

    @staticmethod
    def create_standard(timeout: float = 2.0, retries: int = 1) -> Resolver:
        return Resolver(timeout=timeout, retries=retries)

    @staticmethod
    def create_bulk(timeout: float = 1.5, retries: int = 2) -> Resolver:
        """Optimised for high-volume scanning – lower per-query timeout but more retries."""
        return Resolver(timeout=timeout, retries=retries)

    @staticmethod
    def from_config(config: Dict[str, Any]) -> Resolver:
        """Load resolver from a config dict."""
        return Resolver(
            timeout=config.get('dns_timeout', 2.0),
            retries=config.get('dns_retries', 1)
        )