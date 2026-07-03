# Build, Test, SBOM, and Audit Guide

## Prerequisites

```bash
# Python 3.10+
python --version

# pip
pip --version
```

## Installation for Development

```bash
git clone https://github.com/eurothrottle/advancement-machine.git
cd advancement-machine
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests with coverage
pytest -v

# Run specific test modules
pytest tests/test_temporal_scheduler.py -v
pytest tests/test_phase1_task_decomposition.py -v
pytest tests/test_phase2_core.py -v

# With coverage report
pytest --cov=advancement_machine --cov-report=term-missing
```

## Code Quality

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/ --ignore-missing-imports
```

## Building

```bash
# Install build tool
pip install build

# Build wheel and sdist
python -m build

# Output in dist/
ls dist/
```

## SBOM Generation

```bash
# Generate Software Bill of Materials
python -c "
from advancement_machine.build_system import BuildSystem
import json
b = BuildSystem()
sbom = b.generate_sbom()
with open('sbom.json', 'w') as f:
    json.dump(sbom, f, indent=2)
print('SBOM generated: sbom.json')
"
```

## Supply Chain Verification

```python
from advancement_machine.supply_chain import SupplyChainValidator

validator = SupplyChainValidator("sbom.json")

# Verify artifact checksums
is_valid = validator.verify_checksum("artifact.whl", "sha256:...")

# Check dependency freshness
results = validator.check_all_freshness()
```

## CI/CD Pipeline

The project uses GitHub Actions for continuous integration:

1. **Lint**: black, ruff, mypy checks
2. **Test**: Multi-OS (Ubuntu, Windows, macOS) x Multi-Python (3.10, 3.11)
3. **Build**: Wheel and sdist generation
4. **SBOM**: Software Bill of Materials generation
5. **Release Gate**: Checksum verification and smoke test

See `.github/workflows/ci.yml` for the full pipeline configuration.
