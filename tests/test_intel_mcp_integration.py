"""
Integration tests for intel_mcp modules.

Tests:
  - Pattern memory functionality
  - Repository collector & classifier
  - Scoring and ranking
  - Pattern extraction
  - Full pipeline integration
"""

import pytest
import tempfile
from pathlib import Path
from advancement_machine.intel_mcp import (
    PatternMemory,
    ExtractedPattern,
    RepoClassifier,
    RelevanceScorer,
    PatternExtractor,
    DNAProfiler,
    Comparator,
    SuggestionEngine,
    LearningLog,
)


class TestPatternMemory:
    """Pattern memory + deduplication tests."""
    
    def test_pattern_memory_initialization(self):
        """Test pattern memory initializes with SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            pm = PatternMemory(db_path=db_path)
            assert pm.db_path == db_path
            pm.close()
    
    def test_store_and_retrieve_pattern(self):
        """Test storing and retrieving patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PatternMemory(db_path=str(Path(tmpdir) / "test.db"))
            
            pattern = ExtractedPattern(
                type="config",
                title="Test Config",
                content="test content",
                confidence=0.9,
                reusability=0.8,
                tags=["test", "demo"]
            )
            
            stored = pm.store_pattern(pattern, "test/repo")
            assert stored.id > 0
            assert stored.hash is not None
            assert stored.reuse_count == 0
            assert stored.query_frequency == 1
            
            pm.close()
    
    def test_deduplication_by_hash(self):
        """Test deduplication: same pattern increments counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PatternMemory(db_path=str(Path(tmpdir) / "test.db"))
            
            pattern = ExtractedPattern(
                type="config",
                title="Config Pattern",
                content="exact content for dedup",
            )
            
            # Store twice
            stored1 = pm.store_pattern(pattern, "repo1")
            stored2 = pm.store_pattern(pattern, "repo2")
            
            # Should be same pattern (deduplicated)
            assert stored1.hash == stored2.hash
            assert stored2.reuse_count == 1
            assert stored2.query_frequency == 2
            
            pm.close()
    
    def test_query_frequency_scoring(self):
        """Test query frequency scoring (commit 31e6cff feature)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PatternMemory(db_path=str(Path(tmpdir) / "test.db"))
            
            pattern = ExtractedPattern(
                type="config",
                title="Scored Pattern",
                content="content"
            )
            
            stored = pm.store_pattern(pattern, "test/repo")
            
            # Increment frequency
            pm.increment_query_frequency(stored.id, "context1")
            pm.increment_query_frequency(stored.id, "context2")
            
            # Get score
            score = pm.get_query_frequency_score(stored.id)
            assert 0.0 <= score <= 1.0
            
            pm.close()
    
    def test_best_pick_deduplication(self):
        """Test best-pick deduplication (commit 31e6cff feature)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PatternMemory(db_path=str(Path(tmpdir) / "test.db"))
            
            # Create multiple config patterns
            for i in range(3):
                pattern = ExtractedPattern(
                    type="config",
                    title=f"Config {i}",
                    content=f"content {i}",
                )
                stored = pm.store_pattern(pattern, f"repo{i}")
                
                # Boost frequency for first one
                if i == 0:
                    for _ in range(5):
                        pm.increment_query_frequency(stored.id)
            
            # Get best picks
            picks = pm.get_best_picks("config", limit=2)
            assert len(picks) <= 2
            # First pick should be highest frequency
            if len(picks) > 1:
                assert picks[0].query_frequency >= picks[1].query_frequency
            
            pm.close()


class TestRepoClassifier:
    """Repository classifier tests."""
    
    def test_classify_repository(self):
        """Test repository classification."""
        classifier = RepoClassifier()
        
        repo = {
            "full_name": "test/mcp-server",
            "name": "mcp-server",
            "description": "An MCP server for AI agent integration",
            "topics": ["mcp", "ai", "development"],
            "stargazers_count": 150
        }
        
        classified = classifier.classify(repo)
        assert "tags" in classified
        assert len(classified["tags"]) > 0
        assert any(tag in classified["tags"] for tag in ["mcp", "ai-ready", "popular"])
    
    def test_batch_classification(self):
        """Test batch classification."""
        classifier = RepoClassifier()
        
        repos = [
            {
                "full_name": "test/mcp-1",
                "description": "MCP server",
                "topics": ["mcp"],
                "stargazers_count": 100
            },
            {
                "full_name": "test/skill-plugin",
                "description": "AI skill plugin",
                "topics": ["skill", "plugin"],
                "stargazers_count": 50
            }
        ]
        
        classified = classifier.classify_batch(repos)
        assert len(classified) == 2
        assert all("tags" in repo for repo in classified)


class TestRelevanceScorer:
    """Relevance scoring tests."""
    
    def test_score_repository(self):
        """Test repository scoring."""
        scorer = RelevanceScorer()
        
        repo = {
            "full_name": "test/project",
            "name": "project",
            "description": "A test project",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues": 5,
            "language": "python",
            "last_updated": "2024-06-01T00:00:00Z",
            "created_at": "2023-01-01T00:00:00Z",
            "topics": ["test"],
            "watchers_count": 10
        }
        
        score = scorer.score(repo)
        assert 0.0 <= score <= 1.0
    
    def test_batch_scoring_with_ranking(self):
        """Test batch scoring and ranking."""
        scorer = RelevanceScorer()
        
        repos = [
            {
                "full_name": "test/popular",
                "stargazers_count": 1000,
                "forks_count": 100,
                "open_issues": 10,
                "language": "python",
                "last_updated": "2024-06-01T00:00:00Z",
                "created_at": "2023-01-01T00:00:00Z",
                "topics": ["mcp"],
                "watchers_count": 50
            },
            {
                "full_name": "test/less-popular",
                "stargazers_count": 50,
                "forks_count": 5,
                "open_issues": 2,
                "language": "javascript",
                "last_updated": "2024-05-01T00:00:00Z",
                "created_at": "2023-06-01T00:00:00Z",
                "topics": ["skill"],
                "watchers_count": 5
            }
        ]
        
        scored = scorer.score_batch(repos)
        assert len(scored) == 2
        # First should have higher score
        assert scored[0]["relevance_score"] >= scored[1]["relevance_score"]


class TestPatternExtractor:
    """Pattern extraction tests."""
    
    def test_extract_from_readme(self):
        """Test extracting patterns from README."""
        extractor = PatternExtractor()
        
        readme = """
# Installation

## npm install

```bash
npm install my-package
```

## Configuration

```json
{
  "name": "my-config",
  "version": "1.0.0"
}
```

## Usage

```python
from my_package import MyClass
obj = MyClass()
```
        """
        
        patterns = extractor.extract_from_readme(readme, "test-repo")
        assert len(patterns) > 0
        assert any(p.type == "config" for p in patterns)


class TestDNAProfiler:
    """DNA profiler tests."""
    
    def test_profile_project(self):
        """Test project profiling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            
            # Create some Python files
            (project_path / "main.py").touch()
            (project_path / "utils.py").touch()
            (project_path / "README.md").touch()
            
            # Create pyproject.toml
            (project_path / "pyproject.toml").write_text("""
[build-system]
requires = ["setuptools"]
""")
            
            profiler = DNAProfiler(str(project_path))
            profile = profiler.profile()
            
            assert "languages" in profile
            assert "python" in profile["languages"]
            assert profile["file_counts"]["python"] == 2


class TestComparator:
    """Comparator tests."""
    
    def test_compare_repositories(self):
        """Test gap analysis."""
        comparator = Comparator()
        
        from advancement_machine.intel_mcp import StoredPattern
        
        external_patterns = [
            StoredPattern(
                id=1,
                hash="hash1",
                type="config",
                title="Config Pattern",
                content="content",
                source_repo="external/repo",
                tags=["test"]
            )
        ]
        
        local_patterns = []
        local_dna = {"languages": ["python"], "frameworks": []}
        
        comparison = comparator.compare(external_patterns, local_patterns, local_dna)
        
        assert "missing" in comparison
        assert "fit_score" in comparison
        assert 0.0 <= comparison["fit_score"] <= 1.0


class TestSuggestionEngine:
    """Suggestion engine tests."""
    
    def test_generate_suggestions(self):
        """Test suggestion generation."""
        engine = SuggestionEngine()
        
        gap_analysis = {
            "missing": [],
            "improvements": [],
            "conflicts": []
        }
        
        suggestions = engine.generate(gap_analysis)
        assert isinstance(suggestions, list)


class TestLearningLog:
    """Learning log tests."""
    
    def test_log_scan(self):
        """Test logging scan operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "learning.db")
            learning_log = LearningLog(db_path=log_path)
            
            learning_log.log_scan(
                query="test mcp",
                repos_found=10,
                patterns_extracted=5,
                top_patterns=["repo1", "repo2"]
            )
            
            scans = learning_log.get_recent_scans(limit=1)
            assert len(scans) == 1
            assert scans[0]["repos_found"] == 10
            
            learning_log.close()
    
    def test_log_suggestion_decision(self):
        """Test logging suggestion decisions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "learning.db")
            learning_log = LearningLog(db_path=log_path)
            
            learning_log.log_suggestion(
                suggestion_id="sugg1",
                title="Test Suggestion",
                level="MICRO",
                status="applied"
            )
            
            summary = learning_log.get_suggestion_summary()
            assert summary.get("applied", 0) > 0
            
            learning_log.close()


class TestFullPipeline:
    """End-to-end pipeline integration tests."""
    
    def test_pattern_memory_pipeline(self):
        """Test full pattern memory pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PatternMemory(db_path=str(Path(tmpdir) / "test.db"))
            
            # Create patterns
            patterns = [
                ExtractedPattern(
                    type="config",
                    title="Config A",
                    content="content a",
                    confidence=0.9
                ),
                ExtractedPattern(
                    type="code",
                    title="Code B",
                    content="content b",
                    confidence=0.8
                )
            ]
            
            # Store all
            stored = []
            for pattern in patterns:
                s = pm.store_pattern(pattern, "test/repo")
                stored.append(s)
            
            # Query best picks
            config_picks = pm.get_best_picks("config", limit=1)
            assert len(config_picks) == 1
            
            # Deduplicate
            deduped = pm.deduplicate_patterns(patterns)
            assert len(deduped) <= len(patterns)
            
            pm.close()
    
    def test_classifier_scorer_pipeline(self):
        """Test classifier + scorer pipeline."""
        classifier = RepoClassifier()
        scorer = RelevanceScorer()
        
        repo = {
            "full_name": "test/mcp-project",
            "name": "mcp-project",
            "description": "MCP server for AI agents",
            "topics": ["mcp", "ai"],
            "stargazers_count": 200,
            "forks_count": 30,
            "open_issues": 5,
            "language": "python",
            "last_updated": "2024-06-01T00:00:00Z",
            "created_at": "2023-01-01T00:00:00Z",
            "watchers_count": 20
        }
        
        # Classify
        classified = classifier.classify(repo)
        assert "tags" in classified
        
        # Score
        score = scorer.score(classified)
        assert 0.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
