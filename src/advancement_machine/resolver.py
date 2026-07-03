import dns.resolver
from typing import List, Optional, NamedTuple

class ResolveResult(NamedTuple):
    subdomain: str
    ip: str
    record_type: str

class DNSError(Exception):
    pass

class Resolver:
    """Lightweight DNS resolver with timeout and type selection."""

    def __init__(self, timeout: float = 2.0, retries: int = 1):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = timeout
        self.resolver.lifetime = timeout * (retries + 1)

    def resolve(self, fqdn: str, record_type: str = 'A') -> Optional[List[ResolveResult]]:
        """Resolve a single FQDN. Returns None on NXDOMAIN or unresolvable."""
        try:
            answers = self.resolver.resolve(fqdn, record_type, raise_on_no_answer=False)
            if not answers:
                return None
            return [
                ResolveResult(fqdn, str(rdata), record_type)
                for rdata in answers
            ]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                dns.exception.Timeout, dns.resolver.NoNameservers):
            return None
        except Exception as e:
            raise DNSError(f'Unexpected DNS error for {fqdn}: {e}') from e