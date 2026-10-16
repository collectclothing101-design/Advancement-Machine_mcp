"""Behavioral and source-integrity regressions for recursive adaptation."""

import ast
import asyncio

import pytest

from advancement_machine.recursive_improvement import RecursiveImprovementEngine

SOURCE = '''def choose(value):
    """Keep the result contract."""
    if value < 0:
        return -value
    else:
        if value == 0:
            return 10
        else:
            return value + 1


def neighbor():
    return "untouched"
'''


@pytest.fixture
def target(tmp_path):
    path = tmp_path / "target.py"
    path.write_text(SOURCE)
    return path


def evaluate(source):
    namespace = {}
    exec(source, namespace)
    assert [namespace["choose"](v) for v in (-2, 0, 3)] == [2, 10, 4]
    return RecursiveImprovementEngine()._score_function(ast.parse(source).body[0])


@pytest.mark.asyncio
async def test_generate_evaluate_deploy_and_repeat(target):
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(target), "choose")
    assert candidate is not None
    assert engine.mutate_function(str(target), "choose") is candidate
    assert engine.summary()["candidates_generated"] == 1
    assert await engine.test_candidate(candidate.id, evaluate)
    assert candidate.score_after < candidate.score_before
    assert engine.deploy_candidate(candidate.id)
    namespace = {}
    exec(target.read_text(), namespace)
    assert namespace["neighbor"]() == "untouched"
    assert namespace["choose"](0) == 10
    assert namespace["choose"].__doc__ == "Keep the result contract."
    # The next adaptation cycle does not emit a no-op.
    assert engine.mutate_function(str(target), "choose") is None
    assert not engine.deploy_candidate(candidate.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["source_changed", "candidate_changed"])
async def test_deployment_refuses_stale_or_unvalidated_content(target, mode):
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(target), "choose")
    assert await engine.test_candidate(candidate.id, evaluate)
    if mode == "source_changed":
        target.write_text(target.read_text() + "\n# concurrent edit\n")
    else:
        candidate.mutated_source += "\nraise RuntimeError('changed')"
    before = target.read_bytes()
    assert not engine.deploy_candidate(candidate.id)
    assert target.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1, 10])
async def test_invalid_or_equal_scores_fail(target, score):
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(target), "choose")
    assert not await engine.test_candidate(candidate.id, lambda _: score)
    assert candidate.status == "failed"
    assert not engine.deploy_candidate(candidate.id)


@pytest.mark.asyncio
async def test_async_evaluator_and_concurrent_evaluation(target):
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(target), "choose")

    async def evaluator(source):
        await asyncio.sleep(0)
        return evaluate(source)

    outcomes = await asyncio.gather(
        *(engine.test_candidate(candidate.id, evaluator) for _ in range(2))
    )
    assert outcomes == [True, False]


@pytest.mark.asyncio
async def test_cancelled_evaluation_cannot_deploy(target):
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(target), "choose")

    async def evaluator(_):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await engine.test_candidate(candidate.id, evaluator)
    assert candidate.status == "failed"
    assert not engine.deploy_candidate(candidate.id)


@pytest.mark.asyncio
async def test_decorated_async_method_preserves_class_neighbors(tmp_path):
    path = tmp_path / "methods.py"
    path.write_text("""class Example:
    @staticmethod
    async def choose(value):
        if value:
            return 1
        else:
            return 2

    def neighbor(self):
        return 3
""")
    engine = RecursiveImprovementEngine()
    candidate = engine.mutate_function(str(path), "choose")
    scores = iter([2, 1])
    assert await engine.test_candidate(candidate.id, lambda _: next(scores))
    assert engine.deploy_candidate(candidate.id)
    namespace = {}
    exec(path.read_text(), namespace)
    assert await namespace["Example"].choose(False) == 2
    assert namespace["Example"]().neighbor() == 3


def test_ambiguous_targets_and_unsafe_loop_are_ignored(tmp_path):
    path = tmp_path / "ambiguous.py"
    path.write_text(
        SOURCE + "\nclass Other:\n" + "\n".join("    " + line for line in SOURCE.splitlines())
    )
    engine = RecursiveImprovementEngine()
    assert engine.mutate_function(str(path), "choose") is None
    path.write_text(
        "def gather(values):\n    result = []\n    for value in values:\n        result.append(value)\n    return result\n"
    )
    assert engine.mutate_function(str(path), "gather") is None


def test_metric_direction_zero_baseline_and_bounded_history():
    engine = RecursiveImprovementEngine()
    for name, old, new in [("throughput", 10, 5), ("error_rate", 0, 0.5), ("execution_time", 1, 2)]:
        for value in [old] * 10 + [new] * 10:
            engine.record_metric(name, value)
    assert {b["metric"] for b in engine.analyze_bottlenecks()} == {
        "throughput",
        "error_rate",
        "execution_time",
    }
    for _ in range(1010):
        engine.record_metric("throughput", 20)
    assert len(engine.metrics["throughput"]) == 1000
    assert "throughput" not in {b["metric"] for b in engine.analyze_bottlenecks()}
    for value in (float("nan"), float("inf"), -1):
        with pytest.raises(ValueError):
            engine.record_metric("error_rate", value)
