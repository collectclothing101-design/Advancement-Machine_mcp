import os
import sys
import platform
import json
from pathlib import Path
from .config import ConfigManager
from . import __app_name__, __version__

class Doctor:
    def run(self) -> dict:
        cfg = ConfigManager.get()
        result = {
            "app": __app_name__,
            "version": __version__,
            "platform": {
                "os": platform.system(),
                "release": platform.release(),
                "architecture": platform.machine(),
                "python": sys.version,
            },
            "config": {
                "file_loaded": [str(p) for p in ConfigManager._files_loaded] if hasattr(ConfigManager, '_files_loaded') else [],
                "valid": True,
                "dump": cfg.model_dump(mode="json"),
            },
            "paths": {
                "cwd": str(Path.cwd()),
                "plugin_dir": str(Path(cfg.plugin_dir).resolve()),
                "plugin_dir_exists": Path(cfg.plugin_dir).exists(),
                "log_dir_exists": Path(cfg.log_dir).exists(),
            },
            "network": {
                "dns": self._check_dns(),
            },
            "healthy": True,
        }
        return result

    def _check_dns(self) -> bool:
        try:
            import socket
            socket.getaddrinfo("google.com", 80)
            return True
        except Exception:
            return False

    def print_report(self) -> None:
        report = self.run()
        print(json.dumps(report, indent=2))