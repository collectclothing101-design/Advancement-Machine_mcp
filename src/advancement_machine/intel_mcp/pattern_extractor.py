"""
Pattern Extractor: Extract patterns from repository files.

Patterns detected:
  - Configuration patterns (CLAUDE.md, MCP configs, plugins)
  - Code patterns (common utilities, helper functions)
  - Architecture patterns (directory structures, design)
"""

import re
import logging
from typing import List, Dict, Any, Optional
from .pattern_memory import ExtractedPattern

logger = logging.getLogger(__name__)


class PatternExtractor:
    """Extract patterns from repository content."""
    
    PATTERN_TYPES = ["config", "code", "architecture", "workflow", "documentation"]
    
    def __init__(self):
        logger.debug("PatternExtractor initialized")
    
    def extract_from_readme(self, readme_content: str, repo_name: str) -> List[ExtractedPattern]:
        """
        Extract patterns from README.
        
        Looks for:
          - Installation instructions
          - Configuration examples
          - Usage patterns
          - Architecture diagrams
        """
        patterns = []
        
        if not readme_content:
            return patterns
        
        # Extract installation blocks
        install_blocks = re.findall(
            r"(^#{1,3}\s*installation.*?(?=^#{1,3}|\Z))",
            readme_content,
            re.IGNORECASE | re.MULTILINE | re.DOTALL
        )
        
        for block in install_blocks:
            if "npm install" in block or "pip install" in block or "docker" in block:
                patterns.append(ExtractedPattern(
                    type="config",
                    title=f"{repo_name}: Installation Setup",
                    content=block[:500],
                    confidence=0.8,
                    reusability=0.9,
                    tags=["installation", "setup", "onboarding"]
                ))
        
        # Extract configuration examples
        config_blocks = re.findall(
            r"```(yaml|json|toml|env)\n(.*?)\n```",
            readme_content,
            re.DOTALL
        )
        
        for lang, config in config_blocks:
            patterns.append(ExtractedPattern(
                type="config",
                title=f"{repo_name}: {lang.upper()} Configuration",
                content=config[:500],
                confidence=0.7,
                reusability=0.8,
                tags=["configuration", lang.lower()]
            ))
        
        # Extract code examples
        code_blocks = re.findall(
            r"```(python|typescript|javascript|go|rust)\n(.*?)\n```",
            readme_content,
            re.DOTALL
        )
        
        for lang, code in code_blocks:
            patterns.append(ExtractedPattern(
                type="code",
                title=f"{repo_name}: {lang.title()} Example",
                content=code[:500],
                confidence=0.7,
                reusability=0.6,
                tags=["code", "example", lang.lower()]
            ))
        
        return patterns
    
    def extract_from_package_json(self, content: str, repo_name: str) -> List[ExtractedPattern]:
        """Extract patterns from package.json (Node.js projects)."""
        patterns = []
        
        try:
            import json
            pkg = json.loads(content)
            
            # Extract scripts (common workflows)
            scripts = pkg.get("scripts", {})
            if scripts:
                patterns.append(ExtractedPattern(
                    type="workflow",
                    title=f"{repo_name}: Build/Test Scripts",
                    content=json.dumps(scripts, indent=2)[:500],
                    confidence=0.8,
                    reusability=0.7,
                    tags=["npm", "scripts", "workflow"]
                ))
            
            # Extract dependencies (common libraries)
            deps = pkg.get("dependencies", {})
            if deps:
                patterns.append(ExtractedPattern(
                    type="architecture",
                    title=f"{repo_name}: Dependencies Stack",
                    content=json.dumps(dict(list(deps.items())[:10]), indent=2),
                    confidence=0.6,
                    reusability=0.5,
                    tags=["dependencies", "npm", "stack"]
                ))
        
        except Exception as e:
            logger.debug(f"Error parsing package.json: {e}")
        
        return patterns
    
    def extract_from_pyproject_toml(self, content: str, repo_name: str) -> List[ExtractedPattern]:
        """Extract patterns from pyproject.toml (Python projects)."""
        patterns = []
        
        try:
            # Simple parsing (would need toml library for proper parsing)
            if "[build-system]" in content:
                patterns.append(ExtractedPattern(
                    type="architecture",
                    title=f"{repo_name}: Python Build Configuration",
                    content=content[:500],
                    confidence=0.7,
                    reusability=0.6,
                    tags=["python", "build", "pyproject"]
                ))
            
            if "[tool.pytest" in content:
                patterns.append(ExtractedPattern(
                    type="workflow",
                    title=f"{repo_name}: Python Testing Configuration",
                    content=content[:500],
                    confidence=0.7,
                    reusability=0.7,
                    tags=["python", "pytest", "testing"]
                ))
        
        except Exception as e:
            logger.debug(f"Error parsing pyproject.toml: {e}")
        
        return patterns
    
    def extract_from_dockerfile(self, content: str, repo_name: str) -> List[ExtractedPattern]:
        """Extract patterns from Dockerfile."""
        patterns = []
        
        if not content:
            return patterns
        
        patterns.append(ExtractedPattern(
            type="architecture",
            title=f"{repo_name}: Docker Configuration",
            content=content[:500],
            confidence=0.8,
            reusability=0.7,
            tags=["docker", "containerization", "deployment"]
        ))
        
        return patterns
    
    def extract_mcp_configuration(self, content: str, repo_name: str) -> List[ExtractedPattern]:
        """
        Extract MCP server configurations.
        
        Looks for MCP-specific patterns in config files.
        """
        patterns = []
        
        if "mcpServers" in content or "mcp" in content.lower():
            patterns.append(ExtractedPattern(
                type="config",
                title=f"{repo_name}: MCP Server Configuration",
                content=content[:500],
                confidence=0.9,
                reusability=0.8,
                tags=["mcp", "server", "configuration"]
            ))
        
        return patterns
