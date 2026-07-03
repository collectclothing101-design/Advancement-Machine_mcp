import importlib
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional
from .errors import PluginLoadError
from .logging import setup_logging

logger = setup_logging()

class Plugin:
    def __init__(self, name: str, module):
        self.name = name
        self.module = module
        self._hooks: Dict[str, list] = {}
        self._discover_hooks()

    def _discover_hooks(self):
        for attr_name in dir(self.module):
            obj = getattr(self.module, attr_name)
            if callable(obj) and hasattr(obj, '_plugin_hook'):
                hook_name = obj._plugin_hook
                self._hooks.setdefault(hook_name, []).append(obj)

    def get_hooks(self, hook_name: str) -> list:
        return self._hooks.get(hook_name, [])

class PluginManager:
    def __init__(self, plugin_dir: str, hot_reload: bool = False):
        self.plugin_dir = plugin_dir
        self.hot_reload = hot_reload
        self._plugins: Dict[str, Plugin] = {}
        self._discover()

    def _discover(self):
        pdir = Path(self.plugin_dir)
        if not pdir.exists():
            logger.warning(f"Plugin directory '{self.plugin_dir}' does not exist.")
            return
        for entry in pdir.iterdir():
            if entry.suffix == ".py" and entry.stem != "__init__":
                self._load_plugin(entry.stem)
        if self.hot_reload:
            self._start_watcher(pdir)

    def _load_plugin(self, name: str):
        pdir = Path(self.plugin_dir)
        entry = pdir / f"{name}.py"
        if not entry.exists():
            return
        try:
            spec = importlib.util.spec_from_file_location(name, entry)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            self._plugins[name] = Plugin(name, module)
            logger.info(f"Loaded plugin: {name}")
        except Exception as e:
            raise PluginLoadError(name, str(e))

    def _start_watcher(self, pdir: Path):
        last_mtime = {p: (pdir / f"{p}.py").stat().st_mtime for p in list(self._plugins.keys())}

        def watch():
            while True:
                time.sleep(2)
                for name in list(last_mtime.keys()):
                    filepath = pdir / f"{name}.py"
                    if filepath.exists() and filepath.stat().st_mtime > last_mtime[name]:
                        logger.info(f"Hot-reload detected for plugin '{name}'")
                        try:
                            spec = importlib.util.spec_from_file_location(name, filepath)
                            module = importlib.util.module_from_spec(spec)
                            sys.modules[name] = module
                            spec.loader.exec_module(module)
                            self._plugins[name] = Plugin(name, module)
                            last_mtime[name] = filepath.stat().st_mtime
                        except Exception as e:
                            logger.error(f"Failed to reload plugin '{name}': {e}")
        t = threading.Thread(target=watch, daemon=True)
        t.start()

    def get(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def all(self) -> list:
        return list(self._plugins.values())

    async def reload_plugin(self, name: str):
        self._load_plugin(name)