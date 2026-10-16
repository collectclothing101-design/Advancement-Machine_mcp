# Workflow feedback and recursive adaptation

`WorkflowEngine` optionally shares a `RecursiveImprovementEngine`. Each workflow
run records elapsed seconds, the fraction of failed or skipped nodes, and
completed nodes per second. Histories retain at most 1,000 samples per metric.
Bottleneck analysis compares adjacent windows of ten runs and reports regressions
above 20%. Lower throughput is a regression; lower latency and error rate are improvements.
Compare runs of similar workloads for useful signals.

```python
from advancement_machine.recursive_improvement import RecursiveImprovementEngine
from advancement_machine.workflow_engine import WorkflowEngine

adaptation = RecursiveImprovementEngine()
workflows = WorkflowEngine(improvement_engine=adaptation)
# Register your async tool executor, compose workflows, and execute them.
# After at least 20 runs:
regressions = adaptation.analyze_bottlenecks()
targets = adaptation.scan_for_mutation_targets()
```

Workflow graphs are checked for missing dependencies and cycles before tools
execute. Independent nodes execute concurrently. Failed nodes cause their
descendants to be skipped; independent branches continue. Every run resets node
results and errors, and copies the initial context. Duplicate node IDs and
concurrent execution of the same workflow are rejected. Sub-workflow failures
propagate to their parent.

## Candidate lifecycle

1. Call `mutate_function(file_path, function_name)` to propose a change. Names
   must identify one function in the file. Async functions and methods are supported.
2. Call `await test_candidate(candidate.id, evaluator)`. The evaluator receives
   original source, then mutated source, and must check behavioral equivalence
   (raising on failure) and return a finite nonnegative score. **Lower is better**
   for both evaluations. Async evaluators are supported. Identical scores fail.
3. Call `deploy_candidate(candidate.id)` explicitly after validation. It checks
   the source fingerprint and validated candidate, compiles the complete module,
   preserves neighboring definitions and file permissions, and replaces the file
   atomically. A changed source file requires generating a fresh candidate.
4. Repeat against the updated source to find further simplifications. Candidate
   IDs are content based; repeated generation returns the existing candidate.
   Unchanged functions produce no candidate.

The current transformation flattens `else` blocks after an unconditional
`return` or `raise`. It preserves expression order and introduces no new names.
The old random append-loop rewrite and synthetic `self` guards have been removed.
Structural complexity is measured from AST nesting, independently of line numbers.

Evaluation runs in the caller's process: it is **not a sandbox**. Supply a trusted
evaluator with meaningful behavioral checks and a consistent objective such as
complexity, latency, or memory usage. Deployment writes source on disk; already
imported modules require reloading or restarting through the application's normal
lifecycle. The metric loop does not automatically execute or deploy generated code.
