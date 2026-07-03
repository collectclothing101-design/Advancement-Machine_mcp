"""
DNA Profiler: Detect local project tech stack.

Scans project files to determine:
  - Languages (Python, TypeScript, Go, Rust, etc.)
  - Frameworks (Flask, FastAPI, Express, etc.)
  - Build systems (pip, npm, cargo, etc.)
  - Testing frameworks (pytest, jest, etc.)
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class DNAProfiler:
    """Detect local project technology stack."""
    
    LANGUAGE_PATTERNS = {
        "python": {
            "files": ["*.py", "pyproject.toml", "setup.py", "requirements.txt"],
            "keywords": ["import", "def ", "class "]
        },
        "typescript": {
            "files": ["*.ts", "tsconfig.json"],
            "keywords": ["interface", "type ", "async"]
        },
        "javascript": {
            "files": ["*.js", "package.json"],
            "keywords": ["const ", "async", "import"]
        },
        "go": {
            "files": ["*.go", "go.mod"],
            "keywords": ["package ", "func ", "import"]
        },
        "rust": {
            "files": ["*.rs", "Cargo.toml"],
            "keywords": ["fn ", "struct ", "impl"]
        },
    }
    
    FRAMEWORK_PATTERNS = {
        "fastapi": ["fastapi", "from fastapi"],
        "flask": ["flask", "from flask"],
        "django": ["django", "from django"],
        "express": ["express", "require('express')"],
        "mcp": ["mcp", "mcp server", "mcp tools"],
        "anthropic": ["anthropic", "from anthropic"],
    }
    
    def __init__(self, project_path: str = "."):
        """Initialize profiler with project path."""
        self.project_path = Path(project_path)
        logger.debug(f"DNAProfiler initialized for {self.project_path}")
    
    def profile(self) -> Dict[str, any]:
        """
        Profile local project stack.
        
        Returns:
            Dict with:
              - languages: detected languages
              - frameworks: detected frameworks
              - files: file count by type
              - estimated_maturity: 0-1 score
        """
        languages = self._detect_languages()
        frameworks = self._detect_frameworks()
        files = self._count_files()
        
        maturity = self._estimate_maturity(languages, frameworks, files)
        
        return {
            "languages": languages,
            "frameworks": frameworks,
            "file_counts": files,
            "estimated_maturity": maturity,
            "profile_path": str(self.project_path)
        }
    
    def _detect_languages(self) -> List[str]:
        """Detect languages in project."""
        detected = set()
        
        for lang, patterns in self.LANGUAGE_PATTERNS.items():
            for pattern in patterns["files"]:
                if self._glob_exists(pattern):
                    detected.add(lang)
                    break
        
        return sorted(list(detected))
    
    def _detect_frameworks(self) -> List[str]:
        """Detect frameworks in project."""
        detected = set()
        
        # Check common config/manifest files
        for framework, keywords in self.FRAMEWORK_PATTERNS.items():
            for keyword in keywords:
                if self._text_search(keyword):
                    detected.add(framework)
                    break
        
        return sorted(list(detected))
    
    def _count_files(self) -> Dict[str, int]:
        """Count files by type."""
        counts = {
            "python": 0,
            "typescript": 0,
            "javascript": 0,
            "json": 0,
            "yaml": 0,
            "markdown": 0
        }
        
        for file_path in self.project_path.rglob("*"):
            if file_path.is_file():
                suffix = file_path.suffix.lower()
                if suffix == ".py":
                    counts["python"] += 1
                elif suffix == ".ts":
                    counts["typescript"] += 1
                elif suffix == ".js":
                    counts["javascript"] += 1
                elif suffix == ".json":
                    counts["json"] += 1
                elif suffix in [".yaml", ".yml"]:
                    counts["yaml"] += 1
                elif suffix in [".md", ".markdown"]:
                    counts["markdown"] += 1
        
        return {k: v for k, v in counts.items() if v > 0}
    
    def _estimate_maturity(self, languages: List[str], frameworks: List[str], files: Dict[str, int]) -> float:
        """Estimate project maturity (0-1)."""
        score = 0.5
        
        # Multiple languages = more mature
        if len(languages) >= 2:
            score += 0.2
        
        # Known frameworks = more mature
        if len(frameworks) > 0:
            score += 0.15
        
        # Markdown docs = more mature
        if files.get("markdown", 0) > 0:
            score += 0.1
        
        # Tests present = more mature
        if self._text_search("test") or self._text_search("spec"):
            score += 0.15
        
        return min(1.0, score)
    
    def _glob_exists(self, pattern: str) -> bool:
        """Check if files matching glob pattern exist."""
        try:
            return any(self.project_path.glob(f"**/{pattern}"))
        except:
            return False
    
    def _text_search(self, keyword: str) -> bool:
        """Search for keyword in common config files."""
        config_files = [
            "package.json", "pyproject.toml", "setup.py",
            "go.mod", "Cargo.toml", "README.md",
            ".github/workflows/*"
        ]
        
        for config_file in config_files:
            for file_path in self.project_path.glob(config_file):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        if keyword.lower() in f.read().lower():
                            return True
                except:
                    continue
        
        return False
