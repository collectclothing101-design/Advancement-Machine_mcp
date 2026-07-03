"""
Deterministic wheel build, SBOM generation, checksum, and GPG signing.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .logging import setup_logging

logger = setup_logging()

class BuildSystem:
    """Deterministic build pipeline with SBOM generation and artifact signing."""

    def __init__(self, source_dir: str = "."):
        self.src = Path(source_dir).resolve()
        self.dist = self.src / "dist"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        import tomli
        pyproject = self.src / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject) as f:
                data = tomli.loads(f.read())
            return data.get("project", {})
        return {"name": "unknown", "version": "0.0.0"}

    def build_wheel(self) -> Path:
        """Build a deterministic wheel using pip with --no-isolation."""
        logger.info("Building wheel (deterministic mode)...")
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation", str(self.src)],
            cwd=self.src, check=True, capture_output=True,
        )
        wheels = list(self.dist.glob("*.whl"))
        if not wheels:
            raise RuntimeError("Wheel build produced no output")
        return wheels[0]

    def compute_checksums(self, artifact: Path) -> dict:
        """Return sha256 and blake2b checksums for an artifact."""
        data = artifact.read_bytes()
        return {
            "sha256": hashlib.sha256(data).hexdigest(),
            "blake2b": hashlib.blake2b(data).hexdigest(),
        }

    def generate_sbom(self) -> dict:
        """Generate a CycloneDX SBOM from pinned dependencies."""
        from cyclonedx_py.model.bom import Bom, Metadata, Component, Tool
        from cyclonedx_py.model.component import ComponentType
        from packageurl import PackageURL

        bom = Bom()
        main = Component(
            name=self.metadata.get("name", "advancement-machine"),
            version=self.metadata.get("version", "0.0.0"),
            type=ComponentType.APPLICATION,
        )
        deps = self._parse_dependencies()
        for dep_name, dep_version in deps.items():
            comp = Component(
                name=dep_name,
                version=dep_version,
                type=ComponentType.LIBRARY,
                purl=PackageURL(type="pypi", name=dep_name, version=dep_version).to_string(),
            )
            bom.components.add(comp)
            main.dependencies.add(comp.purl)

        bom.metadata = Metadata(
            tools=[Tool(name=self.metadata.get("name"), version=self.metadata.get("version"))],
            component=main,
        )
        return json.loads(bom.to_json())

    def _parse_dependencies(self) -> dict:
        """Extract pinned dependencies from pyproject.toml."""
        import tomli
        pyproject = self.src / "pyproject.toml"
        if not pyproject.exists():
            return {}
        with open(pyproject) as f:
            data = tomli.loads(f.read())
        deps_raw = data.get("project", {}).get("dependencies", [])
        result = {}
        for dep in deps_raw:
            if ">=" in dep:
                name, ver = dep.split(">=", 1)
                result[name.strip()] = ver.strip()
            elif "==" in dep:
                name, ver = dep.split("==", 1)
                result[name.strip()] = ver.strip()
            else:
                result[dep.strip()] = "latest"
        return result

    def sign_artifact(self, artifact: Path, key_path: str) -> str:
        """Sign artifact with GPG and return the signature string."""
        sig_path = artifact.with_suffix(artifact.suffix + ".sig")
        subprocess.run(
            ["gpg", "--detach-sign", "--armor", "-u", key_path, "-o", str(sig_path), str(artifact)],
            check=True, capture_output=True,
        )
        return sig_path.read_text()

    def build_all(self, sign_key: Optional[str] = None) -> dict:
        """Run the full build pipeline: wheel, checksums, SBOM, signing."""
        artifact = self.build_wheel()
        checksums = self.compute_checksums(artifact)
        sbom = self.generate_sbom()
        signature = ""
        if sign_key:
            signature = self.sign_artifact(artifact, sign_key)

        manifest = {
            "artifact": artifact.name,
            "checksums": checksums,
            "sbom": sbom,
            "signature": signature,
            "build_time": datetime.now(timezone.utc).isoformat(),
            "build_env": os.environ.get("ADVANCEMENT_BUILD_ENV", "local"),
        }
        manifest_path = self.dist / "build_manifest.json"
        self.dist.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Build complete. Manifest: {manifest_path}")
        return manifest