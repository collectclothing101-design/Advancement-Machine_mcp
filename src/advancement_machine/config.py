import os
import json
import yaml
import tomli
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, Optional, List

class AppConfig(BaseModel):
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="./logs")
    plugin_dir: str = Field(default="./plugins")
    hot_reload: bool = Field(default=False)
    memory_db: str = Field(default="./memory.db")
    registry_urls: str = Field(default="")
    extra: Dict[str, Any] = Field(default_factory=dict)

class ConfigManager:
    _instance = None

    def __init__(self):
        self._config: Optional[AppConfig] = None
        self._files_loaded: List[Path] = []

    @classmethod
    def get(cls) -> AppConfig:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load()
        return cls._instance._config

    def _load(self) -> None:
        raw = AppConfig().model_dump()
        for path in [Path("advancement.yml"), Path("advancement.yaml"),
                     Path("advancement.json"), Path("advancement.toml")]:
            if path.exists():
                self._files_loaded.append(path)
                with open(path) as f:
                    if path.suffix in (".yml", ".yaml"):
                        raw.update(yaml.safe_load(f))
                    elif path.suffix == ".json":
                        raw.update(json.load(f))
                    elif path.suffix == ".toml":
                        raw.update(tomli.loads(f.read()))
                break
        prefix = "ADVANCEMENT_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                raw[config_key] = value
        try:
            self._config = AppConfig(**raw)
        except ValidationError as e:
            print(f"[config] Invalid configuration: {e}")
            raise SystemExit(1)

    @staticmethod
    def dump() -> str:
        return json.dumps(AppConfig.get().model_dump(), indent=2)