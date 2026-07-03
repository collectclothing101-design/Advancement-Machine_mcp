from typing import List, Set
import itertools

class CandidateGenerator:
    """Generates subdomain candidates from wordlists and patterns."""

    def __init__(self, domain: str):
        self.domain = domain.rstrip('.')

    def from_wordlist(self, words: List[str]) -> List[str]:
        """Prepend each word to the domain."""
        return [f'{w}.{self.domain}' for w in words if w and not w.isspace()]

    def from_permutations(self, word: str, suffixes: Set[str] = None) -> List[str]:
        """Generate variations for a single word (e.g. hyphenation, number suffixes)."""
        if suffixes is None:
            suffixes = {'-dev', '-staging', '-test', '1', '2', 'backup', 'old'}
        base = word
        variants = {base}
        variants.update(f'{base}-{s}' for s in suffixes if not s.isdigit())
        variants.update(f'{base}{s}' for s in suffixes if s.isdigit())
        return [f'{v}.{self.domain}' for v in variants]

    def wildcard_check(self, candidate: str) -> str:
        """Return a candidate known to be invalid for wildcard detection."""
        import secrets
        random_label = secrets.token_hex(8)
        return f'{random_label}.{self.domain}'