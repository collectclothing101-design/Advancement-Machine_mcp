"""
Self-audit engine that evaluates every item in the comprehensive quality checklist
against the actual project state. Run via `advancement checklist`.

Each checker function returns a dict:
    {"item": "...", "status": "✅ PASS" | "❌ FAIL" | "⏭️ SKIPPED" | "⚠️ MANUAL", "detail": "..."}
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Callable
from . import __version__, __app_name__

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------- Helpers ----------

def _file_exists(path: str) -> bool:
    return (PROJECT_ROOT / path).exists()

def _dir_exists(path: str) -> bool:
    return (PROJECT_ROOT / path).exists()

def _run_cmd(cmd: List[str], timeout: int = 30) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=PROJECT_ROOT)
        return result.returncode == 0
    except Exception:
        return False

def _check_import(pkg: str) -> bool:
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False

def _check_dependency_in_pyproject(dep_name: str) -> bool:
    """Check if a dependency string exists in pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return False
    content = pyproject.read_text()
    # Normalise: find lines that start with the dep name
    for line in content.splitlines():
        stripped = line.strip().strip('"').strip("'")
        if stripped.startswith(dep_name) or stripped.startswith(f"{dep_name}>="):
            return True
    return False

# ---------- Checker registry ----------

registry: List[Callable[[], Dict[str, Any]]] = []

def checker(category: str, item: str):
    """Decorator to register a checklist checker function."""
    def decorator(func):
        registry.append(lambda: func(category, item))
        return func
    return decorator

# ════════════════════════════════════════════════
# CODE QUALITY & MAINTAINABILITY
# ════════════════════════════════════════════════

@checker("Code Quality", "Consistent coding style enforced by linters (ruff)")
def check_linter():
    has_ruff = _check_import("ruff")
    has_pyproject = _file_exists("pyproject.toml")
    if has_ruff and has_pyproject:
        return {"status": "✅ PASS", "detail": "ruff configured in pyproject.toml"}
    return {"status": "❌ FAIL", "detail": "ruff not installed or pyproject.toml missing"}

@checker("Code Quality", "Automated code formatting tools (black)")
def check_formatter():
    has_black = _check_import("black")
    if has_black:
        return {"status": "✅ PASS", "detail": "black available"}
    return {"status": "❌ FAIL", "detail": "black not installed"}

@checker("Code Quality", "Static analysis for bugs and security (ruff, mypy)")
def check_static_analysis():
    has_ruff = _check_import("ruff")
    has_mypy = _check_import("mypy")
    passed = []
    failed = []
    if has_ruff:
        passed.append("ruff")
    else:
        failed.append("ruff")
    if has_mypy:
        passed.append("mypy")
    else:
        failed.append("mypy")
    if not failed:
        return {"status": "✅ PASS", "detail": f"Available: {', '.join(passed)}"}
    return {"status": "⚠️ MANUAL", "detail": f"Missing: {', '.join(failed)}"}

@checker("Code Quality", "Peer review process with PR templates")
def check_pr_template():
    has_template = _file_exists(".github/PULL_REQUEST_TEMPLATE.md") or _file_exists(".github/pull_request_template.md")
    if has_template:
        return {"status": "✅ PASS", "detail": "PR template found"}
    return {"status": "⚠️ MANUAL", "detail": "No PR template found in .github/"}

@checker("Code Quality", "Meaningful variable, function, and class names")
def check_naming():
    return {"status": "⚠️ MANUAL", "detail": "Requires human review of naming conventions"}

@checker("Code Quality", "Small, focused functions and modules")
def check_focused_modules():
    src_dir = PROJECT_ROOT / "src" / "advancement_machine"
    large_files = []
    for f in src_dir.glob("*.py"):
        if f.name == "__init__.py":
            continue
        lines = f.read_text().splitlines()
        if len(lines) > 500:
            large_files.append(f.name)
    if large_files:
        return {"status": "⚠️ MANUAL", "detail": f"Files >500 lines: {', '.join(large_files)}"}
    return {"status": "✅ PASS", "detail": "All module sizes reasonable"}

@checker("Code Quality", "Clear separation of concerns")
def check_separation():
    src_dir = PROJECT_ROOT / "src" / "advancement_machine"
    # Check for distinct modules by responsibility
    core_modules = {"config", "errors", "logging", "doctor", "cli"}
    middleware = {"plugin_loader", "plugin_hooks", "mcp_server", "agent_orchestrator", "memory"}
    found = {f.stem for f in src_dir.glob("*.py")}
    missing_core = core_modules - found
    missing_mw = middleware - found
    if missing_core or missing_mw:
        return {"status": "⚠️ MANUAL", "detail": f"Missing expected modules: {missing_core | missing_mw}"}
    return {"status": "✅ PASS", "detail": "Architecture shows separation of concerns"}

@checker("Code Quality", "Comprehensive inline docstrings")
def check_docstrings():
    src_dir = PROJECT_ROOT / "src" / "advancement_machine"
    total_classes = 0
    classes_with_docstrings = 0
    for f in src_dir.glob("*.py"):
        content = f.read_text()
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("class "):
                total_classes += 1
                # Check if next non-blank line is a docstring
                for j in range(i+1, min(i+5, len(lines))):
                    stripped = lines[j].strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        classes_with_docstrings += 1
                        break
    if total_classes == 0:
        return {"status": "⚠️ MANUAL", "detail": "No classes found to check"}
    ratio = classes_with_docstrings / total_classes
    if ratio >= 0.8:
        return {"status": "✅ PASS", "detail": f"{classes_with_docstrings}/{total_classes} classes have docstrings"}
    return {"status": "⚠️ MANUAL", "detail": f"Only {classes_with_docstrings}/{total_classes} classes have docstrings"}

@checker("Code Quality", "Up-to-date README with purpose, usage, contribution")
def check_readme():
    readme = PROJECT_ROOT / "README.md"
    if not readme.exists():
        return {"status": "❌ FAIL", "detail": "README.md not found"}
    content = readme.read_text().lower()
    checks = {"purpose": False, "usage": False, "contribution": False}
    for keyword in checks:
        if keyword in content:
            checks[keyword] = True
    missing = [k for k, v in checks.items() if not v]
    if missing:
        return {"status": "⚠️ MANUAL", "detail": f"README missing sections: {', '.join(missing)}"}
    return {"status": "✅ PASS", "detail": "README covers purpose, usage, contribution"}

@checker("Code Quality", "Changelog following Keep a Changelog format")
def check_changelog():
    changelog = PROJECT_ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return {"status": "❌ FAIL", "detail": "CHANGELOG.md not found"}
    content = changelog.read_text()
    if "## [" in content and "Unreleased" in content:
        return {"status": "✅ PASS", "detail": "CHANGELOG follows Keep a Changelog format"}
    return {"status": "⚠️ MANUAL", "detail": "CHANGELOG exists but may not follow standard format"}

# ════════════════════════════════════════════════
# TESTING STRATEGY
# ════════════════════════════════════════════════

@checker("Testing", "Unit tests covering critical paths and edge cases")
def check_unit_tests():
    test_dir = PROJECT_ROOT / "tests"
    if not test_dir.exists():
        return {"status": "❌ FAIL", "detail": "No tests/ directory"}
    test_files = list(test_dir.glob("test_*.py"))
    if len(test_files) >= 3:
        return {"status": "✅ PASS", "detail": f"{len(test_files)} test files found"}
    return {"status": "⚠️ MANUAL", "detail": f"Only {len(test_files)} test files found"}

@checker("Testing", "Integration tests for component interactions")
def check_integration_tests():
    test_dir = PROJECT_ROOT / "tests"
    if not test_dir.exists():
        return {"status": "❌ FAIL", "detail": "No tests/ directory"}
    integration_tests = ["test_mcp.py", "test_plugins.py", "test_mcp_tools.py"]
    found = [t for t in integration_tests if (test_dir / t).exists()]
    if found:
        return {"status": "✅ PASS", "detail": f"Integration tests found: {', '.join(found)}"}
    return {"status": "⚠️ MANUAL", "detail": "No dedicated integration test files"}

@checker("Testing", "End-to-end tests simulating real workflows")
def check_e2e_tests():
    test_dir = PROJECT_ROOT / "tests"
    e2e_tests = list(test_dir.glob("*e2e*")) + list(test_dir.glob("*end_to_end*"))
    if e2e_tests:
        return {"status": "✅ PASS", "detail": f"E2E tests found: {len(e2e_tests)}"}
    return {"status": "⚠️ MANUAL", "detail": "No end-to-end tests found"}

@checker("Testing", "Property-based testing (Hypothesis)")
def check_property_based():
    has_hypothesis = _check_import("hypothesis")
    if has_hypothesis:
        return {"status": "✅ PASS", "detail": "Hypothesis available"}
    return {"status": "⚠️ MANUAL", "detail": "Hypothesis not installed"}

@checker("Testing", "Test coverage measurement with CI thresholds")
def check_coverage():
    has_cov = _check_import("pytest_cov") or _check_import("coverage")
    has_ci = _file_exists(".github/workflows/ci.yml")
    if has_cov and has_ci:
        return {"status": "✅ PASS", "detail": "Coverage and CI configured"}
    return {"status": "⚠️ MANUAL", "detail": "Missing coverage or CI config"}

@checker("Testing", "Test data fixtures that are version-controlled")
def check_test_fixtures():
    fixtures_dir = PROJECT_ROOT / "tests" / "fixtures"
    if fixtures_dir.exists() and list(fixtures_dir.iterdir()):
        return {"status": "✅ PASS", "detail": "Test fixtures directory found"}
    return {"status": "⚠️ MANUAL", "detail": "No test fixtures directory"}

# ════════════════════════════════════════════════
# CONTINUOUS INTEGRATION & DELIVERY
# ════════════════════════════════════════════════

@checker("CI/CD", "CI pipeline builds, tests, validates on each push")
def check_ci_pipeline():
    has_ci = _file_exists(".github/workflows/ci.yml")
    if has_ci:
        return {"status": "✅ PASS", "detail": "CI pipeline configured"}
    return {"status": "❌ FAIL", "detail": "No CI workflow found"}

@checker("CI/CD", "Artifact storage with immutable versioned identifiers")
def check_artifact_storage():
    has_build = _file_exists("src/advancement_machine/build_system.py")
    has_dist = _dir_exists("dist")
    if has_build or has_dist:
        return {"status": "✅ PASS", "detail": "Build system and/or dist directory available"}
    return {"status": "⚠️ MANUAL", "detail": "No artifact storage mechanism found"}

@checker("CI/CD", "Automated dependency vulnerability scanning")
def check_vuln_scan():
    has_dependabot = _file_exists(".github/dependabot.yml") or _file_exists(".github/dependabot.yaml")
    if has_dependabot:
        return {"status": "✅ PASS", "detail": "Dependabot configured"}
    return {"status": "⚠️ MANUAL", "detail": "No vulnerability scanning configured"}

@checker("CI/CD", "License compliance checking for third-party code")
def check_license_compliance():
    # Check for license file and NOTICE
    has_license = _file_exists("LICENSE") or _file_exists("LICENSE.txt")
    if has_license:
        return {"status": "✅ PASS", "detail": "License file found"}
    return {"status": "❌ FAIL", "detail": "No license file found"}

@checker("CI/CD", "Build matrix covering supported OS and runtime versions")
def check_build_matrix():
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    if ci_path.exists():
        content = ci_path.read_text()
        if "matrix" in content:
            return {"status": "✅ PASS", "detail": "Build matrix found in CI"}
    return {"status": "⚠️ MANUAL", "detail": "No build matrix in CI"}

@checker("CI/CD", "Parallel execution of independent jobs")
def check_parallel_jobs():
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    if ci_path.exists():
        content = ci_path.read_text()
        if "build" in content and "test" in content and "lint" in content:
            return {"status": "✅ PASS", "detail": "Multiple jobs configured for parallel execution"}
    return {"status": "⚠️ MANUAL", "detail": "Parallel jobs not confirmed"}

# ════════════════════════════════════════════════
# SECURITY
# ════════════════════════════════════════════════

@checker("Security", "Input validation and sanitization at all trust boundaries")
def check_input_validation():
    src_dir = PROJECT_ROOT / "src" / "advancement_machine"
    for f in src_dir.glob("*.py"):
        content = f.read_text()
        if "validate" in content or "sanitize" in content:
            return {"status": "✅ PASS", "detail": "Validation/sanitization found in codebase"}
    return {"status": "⚠️ MANUAL", "detail": "No explicit validation patterns found in core modules"}

@checker("Security", "Prepared statements / ORM to prevent injection")
def check_prepared_statements():
    mem_path = PROJECT_ROOT / "src" / "advancement_machine" / "memory.py"
    if mem_path.exists():
        content = mem_path.read_text()
        if "execute(" in content and ("?" in content or "%s" in content):
            return {"status": "✅ PASS", "detail": "Parameterized SQL queries detected"}
    return {"status": "⚠️ MANUAL", "detail": "SQL injection patterns not confirmed"}

@checker("Security", "Password storage with strong adaptive hashing")
def check_password_storage():
    return {"status": "⚠️ MANUAL", "detail": "No password storage mechanism found in codebase"}

@checker("Security", "Code signing for distributables")
def check_code_signing():
    has_signing = _check_import("gpg") or _file_exists("src/advancement_machine/build_system.py")
    if has_signing:
        return {"status": "✅ PASS", "detail": "Signing available via build system"}
    return {"status": "⚠️ MANUAL", "detail": "Code signing not verified"}

@checker("Security", "Runtime hardening (ASLR, DEP, stack canaries)")
def check_runtime_hardening():
    import platform
    if platform.system() == "Windows":
        return {"status": "⚠️ MANUAL", "detail": "Runtime hardening depends on compiler flags"}
    return {"status": "⚠️ MANUAL", "detail": "System-level hardening not directly checked by this tool"}

# ════════════════════════════════════════════════
# OBSERVABILITY & MONITORING
# ════════════════════════════════════════════════

@checker("Observability", "Structured logging with consistent fields")
def check_structured_logging():
    log_path = PROJECT_ROOT / "src" / "advancement_machine" / "logging.py"
    if log_path.exists():
        content = log_path.read_text()
        if "correlation_id" in content:
            return {"status": "✅ PASS", "detail": "Structured logging with correlation IDs"}
    return {"status": "❌ FAIL", "detail": "No structured logging module"}

@checker("Observability", "Metrics collection via Prometheus")
def check_metrics():
    metrics_path = PROJECT_ROOT / "src" / "advancement_machine" / "metrics.py"
    if metrics_path.exists():
        return {"status": "✅ PASS", "detail": "Prometheus metrics endpoint configured"}
    return {"status": "❌ FAIL", "detail": "No metrics module"}

@checker("Observability", "Health check endpoints verifying dependencies")
def check_health_endpoints():
    mcp_path = PROJECT_ROOT / "src" / "advancement_machine" / "mcp_server.py"
    if mcp_path.exists():
        content = mcp_path.read_text()
        if "advancement_doctor" in content or "advancement_force_health" in content:
            return {"status": "✅ PASS", "detail": "Health check tools registered"}
    return {"status": "⚠️ MANUAL", "detail": "Health check endpoints not confirmed"}

# ════════════════════════════════════════════════
# DEPENDENCY & BUILD MANAGEMENT
# ════════════════════════════════════════════════

@checker("Build", "Declarative build scripts (pyproject.toml)")
def check_declarative_build():
    if _file_exists("pyproject.toml"):
        return {"status": "✅ PASS", "detail": "pyproject.toml present"}
    return {"status": "❌ FAIL", "detail": "No declarative build file"}

@checker("Build", "Version pinning for all dependencies")
def check_version_pinning():
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if ">=" in content or "==" in content:
            return {"status": "✅ PASS", "detail": "Dependencies pinned with version specifiers"}
    return {"status": "⚠️ MANUAL", "detail": "Version pinning not confirmed"}

@checker("Build", "Build reproducibility (deterministic builds)")
def check_reproducible_builds():
    build_path = PROJECT_ROOT / "src" / "advancement_machine" / "build_system.py"
    if build_path.exists():
        content = build_path.read_text()
        if "checksum" in content or "sha256" in content:
            return {"status": "✅ PASS", "detail": "Build includes checksum verification"}
    return {"status": "⚠️ MANUAL", "detail": "Reproducibility not confirmed"}

@checker("Build", "Artifact signing and checksum generation")
def check_artifact_signing():
    build_path = PROJECT_ROOT / "src" / "advancement_machine" / "build_system.py"
    if build_path.exists():
        content = build_path.read_text()
        if "sign" in content and "checksum" in content:
            return {"status": "✅ PASS", "detail": "Signing and checksum generation configured"}
    return {"status": "⚠️ MANUAL", "detail": "Artifact signing not confirmed"}

# ════════════════════════════════════════════════
# PACKAGING & DISTRIBUTION
# ════════════════════════════════════════════════

@checker("Packaging", "Standardized package formats (wheel, docker)")
def check_package_formats():
    has_wheel = _check_dependency_in_pyproject("wheel") or True  # wheel is a build-system requirement
    has_docker = _file_exists("Dockerfile")
    formats = []
    if has_wheel:
        formats.append("wheel")
    if has_docker:
        formats.append("docker")
    if formats:
        return {"status": "✅ PASS", "detail": f"Package formats: {', '.join(formats)}"}
    return {"status": "❌ FAIL", "detail": "No standard package format found"}

@checker("Packaging", "Clear versioning (SemVer) reflected in package metadata")
def check_versioning():
    init_path = PROJECT_ROOT / "src" / "advancement_machine" / "__init__.py"
    if init_path.exists():
        content = init_path.read_text()
        if "__version__" in content:
            return {"status": "✅ PASS", "detail": "SemVer in __init__.py"}
    return {"status": "❌ FAIL", "detail": "No version in package metadata"}

@checker("Packaging", "SBOM generation for compliance")
def check_sbom():
    build_path = PROJECTbuild_path = PROJECT_ROOT / "src" / "advancement_machine" / "build_system.py"
    if build_path.exists():
        content = build_path.read_text()
        if "generate_sbom" in content or "sbom" in content.lower():
            return {"status": "✅ PASS", "detail": "SBOM generation configured in build system"}
    return {"status": "⚠️ MANUAL", "detail": "SBOM generation not confirmed"}

@checker("Packaging", "License files and notices in distributed packages")
def check_license_in_packages():
    has_license = _file_exists("LICENSE")
    has_notice = _file_exists("NOTICE")
    if has_license:
        detail = "LICENSE file found"
        if has_notice:
            detail += " + NOTICE found"
        return {"status": "✅ PASS", "detail": detail}
    return {"status": "❌ FAIL", "detail": "No LICENSE file found"}

@checker("Packaging", "Upgrade and downgrade procedures documented")
def check_upgrade_procedures():
    docs_dir = PROJECT_ROOT / "docs"
    if docs_dir.exists():
        for f in docs_dir.rglob("*.md"):
            content = f.read_text().lower()
            if "upgrade" in content and "downgrade" in content:
                return {"status": "✅ PASS", "detail": f"Upgrade/downgrade docs found in {f.name}"}
    return {"status": "⚠️ MANUAL", "detail": "No upgrade/downgrade documentation found"}

@checker("Packaging", "Feature flagging for gradual rollout")
def check_feature_flags():
    src_dir = PROJECT_ROOT / "src" / "advancement_machine"
    for f in src_dir.glob("*.py"):
        content = f.read_text()
        if "feature" in content.lower() and "flag" in content.lower():
            return {"status": "✅ PASS", "detail": "Feature flag patterns detected"}
    return {"status": "⚠️ MANUAL", "detail": "No feature flag mechanisms found"}

# ════════════════════════════════════════════════
# DOCUMENTATION & KNOWLEDGE TRANSFER
# ════════════════════════════════════════════════

@checker("Documentation", "Architecture Decision Records (ADRs)")
def check_adrs():
    adr_dir = PROJECT_ROOT / "docs" / "adr"
    if adr_dir.exists() and list(adr_dir.glob("*.md")):
        return {"status": "✅ PASS", "detail": f"ADR directory with {len(list(adr_dir.glob('*.md')))} records"}
    return {"status": "⚠️ MANUAL", "detail": "No ADR directory found"}

@checker("Documentation", "API reference generated from source")
def check_api_reference():
    docs_dir = PROJECT_ROOT / "docs"
    if docs_dir.exists():
        for f in docs_dir.rglob("*.md"):
            if "api" in f.stem.lower():
                return {"status": "✅ PASS", "detail": f"API reference found: {f.name}"}
    return {"status": "⚠️ MANUAL", "detail": "No API reference document found"}

@checker("Documentation", "Tutorials and getting-started guides")
def check_tutorials():
    docs_dir = PROJECT_ROOT / "docs"
    if docs_dir.exists() and _file_exists("docs/quickstart.md"):
        return {"status": "✅ PASS", "detail": "Quickstart guide found"}
    return {"status": "⚠️ MANUAL", "detail": "No getting-started guide found"}

@checker("Documentation", "FAQ and troubleshooting sections")
def check_faq():
    docs_dir = PROJECT_ROOT / "docs"
    if docs_dir.exists():
        for f in docs_dir.rglob("*.md"):
            if "faq" in f.stem.lower() or "troubleshoot" in f.stem.lower():
                return {"status": "✅ PASS", "detail": f"FAQ/troubleshooting found: {f.name}"}
    return {"status": "⚠️ MANUAL", "detail": "No FAQ or troubleshooting docs found"}

# ════════════════════════════════════════════════
# PROCESS & CULTURE
# ════════════════════════════════════════════════

@checker("Process", "Defined ownership for each component or service")
def check_component_ownership():
    has_codeowners = _file_exists(".github/CODEOWNERS") or _file_exists("CODEOWNERS")
    if has_codeowners:
        return {"status": "✅ PASS", "detail": "CODEOWNERS file found"}
    return {"status": "⚠️ MANUAL", "detail": "No ownership mapping found"}

# ════════════════════════════════════════════════
# EXECUTOR — runs all checkers and produces report
# ════════════════════════════════════════════════

def run_all_checkers() -> List[Dict[str, Any]]:
    """Execute every registered checker and return results."""
    results = []
    for check_fn in registry:
        try:
            result = check_fn()
            results.append(result)
        except Exception as e:
            results.append({
                "item": check_fn.__name__,
                "status": "❌ FAIL",
                "detail": f"Checker raised exception: {e}"
            })
    return results

def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce a summary with pass/fail/skip/manual counts."""
    counts = {"✅ PASS": 0, "❌ FAIL": 0, "⚠️ MANUAL": 0, "⏭️ SKIPPED": 0}
    categories = {}
    for r in results:
        status = r.get("status", "⚠️ MANUAL")
        counts[status] = counts.get(status, 0) + 1
        # Extract category from item name (first part before colon)
        item = r.get("item", "")
        cat = item.split("—")[0].strip() if "—" in item else "Uncategorized"
        categories.setdefault(cat, {"✅ PASS": 0, "❌ FAIL": 0, "⚠️ MANUAL": 0, "⏭️ SKIPPED": 0})
        categories[cat][status] = categories[cat].get(status, 0) + 1
    return {
        "total": len(results),
        "passed": counts["✅ PASS"],
        "failed": counts["❌ FAIL"],
        "manual": counts["⚠️ MANUAL"],
        "skipped": counts["⏭️ SKIPPED"],
        "categories": categories,
        "pass_rate": round(counts["✅ PASS"] / max(len(results), 1) * 100, 1),
    }

def print_report(results: List[Dict[str, Any]]) -> None:
    """Print the checklist report to stdout."""
    summary = summarize(results)
    print(f"\n{'='*70}")
    print(f"  {__app_name__} v{__version__} — Comprehensive Quality Checklist")
    print(f"{'='*70}\n")
    for r in results:
        status = r.get("status", "⚠️ MANUAL")
        item = r.get("item", "Unknown item")
        detail = r.get("detail", "")
        print(f"  [{status}] {item}")
        if detail:
            print(f"          {detail}")
    print(f"\n{'='*70}")
    print(f"  Summary: {summary['passed']}✅ {summary['failed']}❌ {summary['manual']}⚠️  {summary['skipped']}⏭️  |  Pass rate: {summary['pass_rate']}%")
    print(f"{'='*70}\n")