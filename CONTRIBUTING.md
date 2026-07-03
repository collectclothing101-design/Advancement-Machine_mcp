# Contributing to Advancement Machine

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a feature branch: `git checkout -b feature/my-feature`
4. Install development dependencies: `pip install -e ".[dev]"`

## Development Setup

```bash
# Install the project in editable mode
pip install -e ".[dev]"

# Run tests
pytest -v

# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/ --ignore-missing-imports
```

## Pull Request Process

1. Ensure all tests pass: `pytest -v`
2. Format your code: `black src/ tests/`
3. Lint your code: `ruff check src/ tests/`
4. Update documentation if needed
5. Submit your pull request

## Code Style

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and small
- Use meaningful variable and function names

## Testing

- Write tests for new features and bug fixes
- Aim for >75% coverage on core modules
- Use pytest fixtures for test setup
- Mock external dependencies

## Reporting Issues

- Use the GitHub issue tracker
- Include steps to reproduce the issue
- Include expected vs actual behavior
- Include Python version and OS information

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
