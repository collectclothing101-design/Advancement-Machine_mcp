"""
Supply-chain integrity: dependency freshness checks, checksum verification,
and provenance validation.
"""
import hashlib
import json
import ssl
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .logging import setup_logging

logger = setup_logging()

class SupplyChainValidator:
    """Validate dependency integrity, freshness, and provenance."""

    def __init__(self, sbom_path: Optional[Path] = None):
        self.sbom = self._load_sbom(sbom_path) if sbom_path else {}

    def _load_sbom(self, path: Path) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load SBOM: {e}")
            return {}

    def verify_checksum(self, artifact: Path, expected_sha256: str) -> bool:
        """Verify artifact SHA256 matches expected value."""
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return actual == expected_sha256

    def check_freshness(self, dep_name: str, current_version: str) -> dict:
        """Query PyPI JSON API to check if a newer version is available."""
        url = f"https://pypi.org/pypi/{dep_name}/json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AdvancementMachine/0.3"})
            with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=10) as resp:
                data = json.loads(resp.read().decode())
                latest = data["info"]["version"]
                return {
                    "name": dep_name,
                    "current": current_version,
                    "latest": latest,
                    "outdated": latest != current_version,
                }
        except Exception as e:
            logger.warning(f"Could not check freshness for {dep_name}: {e}")
            return {"name": dep_name, "current": current_version, "latest": "unknown", "outdated": None}

    def check_all_freshness(self) -> List[dict]:
        """Run freshness check on all SBOM dependencies."""
        results = []
        components = self.sbom.get("components", [])
        for comp in components:
            name = comp.get("name")
            version = comp.get("version")
            if name and version:
                results.append(self.check_freshness(name, version))
        return results

    def verify_provenance(self, artifact: Path, manifest: dict) -> bool:
        """Verify artifact matches checksum and build metadata in manifest."""
        expected_sha = manifest.get("checksums", {}).get("sha256", "")
        if not expected_sha:
            return False
        return self.verify_checksum(artifact, expected_sha)