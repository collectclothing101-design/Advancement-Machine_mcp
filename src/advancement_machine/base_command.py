import abc
from typing import Any, Dict, List, Optional

class BaseCommand(abc.ABC):
    """Every command inherits from this. Strict interface."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._args: Dict[str, Any] = {}

    @abc.abstractmethod
    def configure(self, parser: "argparse.ArgumentParser") -> None:
        """Register command‑specific arguments."""
        ...

    @abc.abstractmethod
    def execute(self, args: Dict[str, Any]) -> Any:
        """Run the command. Returns structured result."""
        ...

    def run(self, raw_args: Optional[List[str]] = None) -> Any:
        import argparse
        parser = argparse.ArgumentParser(prog=self.name, description=self.description)
        self.configure(parser)
        parsed, _ = parser.parse_known_args(raw_args)
        self._args = vars(parsed)
        return self.execute(self._args)

    @property
    def args(self) -> Dict[str, Any]:
        return self._args