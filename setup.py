"""
Setup shim for editable installs from the package directory.

This file allows `pip install -e .` to work when run from inside
the src/advancement_machine/ directory. It reads metadata from
pyproject.toml at the project root.

Usage:
    cd src/advancement_machine/
    pip install -e .
"""
import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

# Find the project root (parent of src/)
src_dir = Path(__file__).resolve().parent
project_root = src_dir.parent.parent  # goes up from src/advancement_machine/ to project root

# Fallback if pyproject.toml not found
if not (project_root / "pyproject.toml").exists():
    # Standalone setup when pyproject.toml is not available
    setup(
        name="advancement-machine",
        version="0.4.0",
        description="Universal MCP/Plugin/Skill engine — deterministic build, SBOM, supply-chain verified",
        author="EuroThrottle",
        license="MIT",
        python_requires=">=3.10",
        packages=find_packages(where=".", include=["advancement_machine*"]),
        package_dir={"": "."},
        install_requires=[
            "pydantic>=2.0",
            "pyyaml>=6.0",
            "tomli>=2.0.0",
            "watchdog>=3.0",
            "rich>=13.0",
            "click>=8.1",
            "mcp>=1.0.0",
            "cyclonedx-python-lib>=3.0",
            "packageurl-python>=0.13",
            "websockets>=12.0",
            "numpy>=1.24",
            "cryptography>=41.0",
        ],
        extras_require={
            "dev": [
                "pytest>=7.0",
                "pytest-asyncio>=0.21",
                "pytest-cov>=4.0",
                "black>=23.0",
                "ruff>=0.1.0",
                "mypy>=1.0",
                "psutil>=5.9",
                "aiohttp>=3.8",
            ],
        },
        entry_points={
            "console_scripts": [
                "advancement = advancement_machine.cli:main",
            ],
        },
        include_package_data=True,
        zip_safe=False,
    )
else:
    # Forward to setuptools with pyproject.toml
    setup()