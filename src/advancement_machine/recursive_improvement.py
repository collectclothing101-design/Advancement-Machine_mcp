"""
Recursive Self-Improvement Engine.

Tracks runtime regressions and proposes deterministic source simplifications.
Callers supply behavioral validation and scoring, then explicitly deploy passed
candidates. Evaluation runs in the caller's process; deployment updates disk
and does not hot-reload already imported code.
"""

import ast
import copy
import hashlib
import inspect
import logging
import math
import os
import stat
import tempfile
import textwrap
import tokenize
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


@dataclass
class ImprovementCandidate:
    id: str
    target_function: str
    original_source: str
    mutated_source: str
    score_before: float
    score_after: float | None = None
    status: str = "pending"  # pending, testing, passed, failed, deployed
    source_hash: str = ""
    target_line: int = 0
    validated_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RecursiveImprovementEngine:
    """Analyzes its own runtime, generates mutations, validates them,
    and deploys successful improvements back into the running system."""

    def __init__(self, watch_dirs: list[str] | None = None) -> None:
        """Initialize the engine with the directories to scan and empty metric history."""
        self.watch_dirs = watch_dirs or ["src/advancement_machine"]
        self.candidates: dict[str, ImprovementCandidate] = {}
        self.metrics: dict[str, list[float]] = {
            "execution_time": [],
            "memory_usage": [],
            "error_rate": [],
            "throughput": [],
        }
        self._generation_count = 0
        self._deployment_count = 0

    def record_metric(self, metric_name: str, value: float) -> None:
        """Keep bounded, finite, nonnegative runtime samples."""
        if metric_name not in self.metrics:
            return
        if not math.isfinite(value) or value < 0:
            raise ValueError("Metrics must be finite and nonnegative")
        self.metrics[metric_name].append(value)
        self.metrics[metric_name] = self.metrics[metric_name][-1000:]

    def analyze_bottlenecks(self) -> list[dict[str, Any]]:
        """Compare adjacent ten-sample windows with metric-specific direction."""
        bottlenecks = []
        for name, values in self.metrics.items():
            if len(values) < 20:
                continue
            avg_recent = sum(values[-10:]) / 10
            avg_older = sum(values[-20:-10]) / 10
            change = avg_older - avg_recent if name == "throughput" else avg_recent - avg_older
            # A zero baseline is a new regression, with a bounded denominator.
            degradation = change / max(avg_older, 1e-12)
            if degradation > 0.2:
                bottlenecks.append(
                    {
                        "metric": name,
                        "degradation": round(degradation * 100, 1),
                        "recent_avg": round(avg_recent, 4),
                        "older_avg": round(avg_older, 4),
                    }
                )
        return sorted(bottlenecks, key=lambda x: x["degradation"], reverse=True)

    def scan_for_mutation_targets(self) -> list[dict[str, Any]]:
        """Scan source files for functions that could be optimized."""
        targets = []
        for watch_dir in self.watch_dirs:
            base = Path(watch_dir)
            for py_file in base.rglob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                try:
                    content, _ = self._read_source(py_file)
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            # Measure complexity
                            num_lines = (node.end_lineno or node.lineno) - node.lineno
                            num_loops = sum(
                                1
                                for n in ast.walk(node)
                                if isinstance(n, (ast.For, ast.While, ast.comprehension))
                            )
                            num_calls = sum(1 for n in ast.walk(node) if isinstance(n, ast.Call))
                            complexity_score = self._score_function(node)
                            targets.append(
                                {
                                    "file": str(py_file),
                                    "function": node.name,
                                    "line": node.lineno,
                                    "lines": num_lines,
                                    "loops": num_loops,
                                    "calls": num_calls,
                                    "complexity": complexity_score,
                                }
                            )
                except (SyntaxError, OSError, UnicodeError):
                    continue
        return sorted(targets, key=lambda x: (x["complexity"], x["file"], x["line"]), reverse=True)[
            :20
        ]

    @staticmethod
    def _read_source(path: Path) -> tuple[str, str]:
        """Read Python source using its encoding cookie or UTF-8 BOM."""
        with cast(TextIOWrapper, tokenize.open(path)) as stream:
            stream.reconfigure(newline="")
            return stream.read(), stream.encoding

    @staticmethod
    def _source_hash(source: str) -> str:
        """Return a stable SHA-256 digest of the given source text."""
        return hashlib.sha256(source.encode()).hexdigest()

    @staticmethod
    def _find_function(tree: ast.AST, name: str) -> Any | None:
        """Return the sole function or method named `name` in `tree`, or None if ambiguous."""
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        # Bare names must identify exactly one function, including methods.
        return matches[0] if len(matches) == 1 else None

    def mutate_function(self, file_path: str, function_name: str) -> ImprovementCandidate | None:
        """Generate a deterministic reduction of nesting; reject no-op candidates."""
        path = Path(file_path)
        try:
            source, _ = self._read_source(path)
            tree = ast.parse(source)
        except (OSError, UnicodeError, SyntaxError):
            return None
        target = self._find_function(tree, function_name)
        if target is None:
            return None
        mutated = self._apply_random_mutation(target)
        if mutated is None:
            return None
        mutated_source = ast.unparse(mutated)
        candidate_id = self._source_hash(f"{path.resolve()}:{source}:{mutated_source}")[:12]
        if candidate_id in self.candidates:
            return self.candidates[candidate_id]
        candidate = ImprovementCandidate(
            id=candidate_id,
            target_function=f"{path.resolve()}:{function_name}",
            original_source=ast.unparse(target),
            mutated_source=mutated_source,
            score_before=self._score_function(target),
            source_hash=self._source_hash(source),
            target_line=target.lineno,
        )
        # Validate the complete module, including indentation and async context.
        try:
            self._validated_replacement(source, target, mutated_source, path)
        except (SyntaxError, ValueError):
            return None
        self.candidates[candidate_id] = candidate
        self._generation_count += 1
        return candidate

    def _apply_random_mutation(self, node: Any) -> Any | None:
        """Compatibility entry point for deterministic, semantics-preserving rewrites."""
        mutated = self._mutate_add_guard_clause(copy.deepcopy(node))
        ast.fix_missing_locations(mutated)
        if ast.dump(node, include_attributes=False) == ast.dump(mutated, include_attributes=False):
            return None
        return mutated

    @staticmethod
    def _mutate_add_guard_clause(node: Any) -> Any:
        """Flatten an else branch when the if body always returns or raises.

        No expressions are reordered or evaluated again, and no new names are
        introduced. Nested function and class scopes are left alone.
        """

        class GuardTransformer(ast.NodeTransformer):
            """Rewrites trailing else branches into guard clauses within a single scope."""

            def visit_FunctionDef(self, child: Any) -> Any:
                """Leave nested function definitions untouched."""
                return child

            def visit_AsyncFunctionDef(self, child: ast.AsyncFunctionDef) -> Any:
                """Leave nested async function definitions untouched."""
                return child

            def visit_ClassDef(self, child: ast.ClassDef) -> Any:
                """Leave nested class definitions untouched."""
                return child

            def visit_If(self, child: ast.If) -> Any:
                """Flatten this if-statement's else branch when the body always exits."""
                self.generic_visit(child)
                if child.orelse and isinstance(child.body[-1], (ast.Return, ast.Raise)):
                    tail = child.orelse
                    child.orelse = []
                    return [child, *tail]
                return child

        transformer = GuardTransformer()
        node.body = [
            result for child in node.body for result in _as_statements(transformer.visit(child))
        ]
        return node

    def _score_function(self, node: Any) -> float:
        """Structural complexity independent of stale AST source line numbers."""

        def score(child: ast.AST, depth: int = 0) -> float:
            """Recursively sum depth-weighted control-flow nodes under `child`."""
            control = isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try))
            return float(control) * (1 + depth) + sum(
                score(n, depth + int(control)) for n in ast.iter_child_nodes(child)
            )

        return score(node)

    async def test_candidate(
        self, candidate_id: str, test_function: Callable[[str], float | Awaitable[float]]
    ) -> bool:
        """Evaluate original and mutation with the same lower-is-better objective.

        The caller must check behavior and raise on invalid results. Callbacks
        may be synchronous or async; this method does not provide isolation.
        """
        candidate = self.candidates.get(candidate_id)
        if not candidate or candidate.status != "pending":
            return False
        candidate.status = "testing"
        original, mutated = candidate.original_source, candidate.mutated_source
        try:
            compile(mutated, "<candidate>", "exec")
            scores = []
            for source in (original, mutated):
                result = test_function(source)
                if inspect.isawaitable(result):
                    result = await result
                if not math.isfinite(result) or result < 0:
                    raise ValueError("Evaluation scores must be finite and nonnegative")
                scores.append(float(result))
            candidate.score_before, candidate.score_after = scores
            if scores[1] < scores[0] and candidate.mutated_source == mutated:
                candidate.validated_hash = self._source_hash(mutated)
                candidate.status = "passed"
                return True
        except Exception as exc:
            logger.warning("Candidate %s failed evaluation: %s", candidate_id, exc)
        finally:
            if candidate.status == "testing":
                candidate.status = "failed"
        return False

    @staticmethod
    def _replace_function(source: str, target: Any, replacement: str) -> str:
        """Splice `replacement` in place of `target` within `source`, preserving indentation and line endings."""
        lines = source.splitlines(keepends=True)
        start = min([target.lineno] + [d.lineno for d in target.decorator_list]) - 1
        indent = lines[start][: target.col_offset]
        # Refuse inline definitions; replacing them could remove sibling code.
        if indent.strip():
            raise ValueError("Inline definitions cannot be replaced")
        newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
        replacement = replacement.replace("\r\n", "\n")
        return (
            "".join(lines[:start])
            + textwrap.indent(replacement, indent).replace("\n", newline)
            + newline
            + "".join(lines[target.end_lineno :])
        )

    def _validated_replacement(self, source: str, target: Any, replacement: str, path: Path) -> str:
        """Reject changes to the candidate AST introduced by embedding it in a module."""
        new_source = self._replace_function(source, target, replacement)
        expected_tree = ast.parse(replacement)
        if len(expected_tree.body) != 1 or not isinstance(
            expected_tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            raise ValueError("Replacement must contain exactly one function")
        embedded_tree = ast.parse(new_source)
        embedded = self._find_function(embedded_tree, target.name)
        if embedded is None or ast.dump(embedded, include_attributes=False) != ast.dump(
            expected_tree.body[0], include_attributes=False
        ):
            raise ValueError("Embedding the replacement changed its function AST")
        compile(embedded_tree, str(path), "exec")
        return new_source

    def deploy_candidate(self, candidate_id: str) -> bool:
        """Replace a validated function; callers must hold exclusive write access.

        Atomic replacement prevents partial writes, but there is no advisory lock
        shared with external writers. Exclusive access must span this entire call,
        including the final source-hash check and replacement.
        """
        candidate = self.candidates.get(candidate_id)
        if not candidate or candidate.status != "passed":
            return False
        if candidate.validated_hash != self._source_hash(candidate.mutated_source):
            return False
        file_path, func_name = candidate.target_function.rsplit(":", 1)
        path = Path(file_path)
        temporary = None
        try:
            source, encoding = self._read_source(path)
            if self._source_hash(source) != candidate.source_hash:
                return False
            target = self._find_function(ast.parse(source), func_name)
            if target is None or target.lineno != candidate.target_line:
                return False
            new_source = self._validated_replacement(source, target, candidate.mutated_source, path)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding=encoding, newline="", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(new_source)
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
            if self._source_hash(self._read_source(path)[0]) != candidate.source_hash:
                return False
            os.replace(temporary, path)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        candidate.status = "deployed"
        self._deployment_count += 1
        return True

    def summary(self) -> dict[str, Any]:
        """Return generation, deployment, and bottleneck counters for this engine."""
        return {
            "candidates_generated": self._generation_count,
            "candidates_deployed": self._deployment_count,
            "active_candidates": len(self.candidates),
            "bottlenecks": self.analyze_bottlenecks(),
            "metrics_tracked": list(self.metrics.keys()),
        }

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return MCP tool schemas exposing this engine's analyze/generate/summary actions."""
        return [
            {
                "name": "recursive_improve_analyze",
                "description": "Analyze system for bottlenecks and mutation targets",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "recursive_improve_generate",
                "description": "Generate improvement candidates for a target function",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "function_name": {"type": "string"},
                    },
                    "required": ["file_path", "function_name"],
                },
            },
            {
                "name": "recursive_improve_summary",
                "description": "Get summary of the recursive improvement engine",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]


def _as_statements(result: Any) -> list[Any]:
    """Normalize a NodeTransformer visit result to a list of statements."""
    return result if isinstance(result, list) else [result]
