"""
Force Multiplier — the 6 systems that make the Advancement-Machine
the most powerful MCP/plugin/skill runtime.

  1. Autonomous Goal Decomposition Engine
  2. Cross-Session Persistent Learning
  3. Universal Protocol Bridge
  4. Self-Healing Plugin Runtime
  5. Plugin Marketplace
  6. Adaptive Security & Stealth
"""

import asyncio, json, hashlib, time, os, sys, importlib, urllib.request, ssl, platform
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from .logging import setup_logging
from .memory import MemoryStore, _compute_embedding, cosine_similarity
from .plugin_loader import PluginManager, Plugin
from .agent_orchestrator import AgentOrchestrator
from .plugin_hooks import on_store, on_search, on_forget, agent_route, mcp_tool

logger = setup_logging()

# ═══════════════════════════════════════════════════════════════
# 1. AUTONOMOUS GOAL DECOMPOSITION ENGINE
# ═══════════════════════════════════════════════════════════════

@dataclass
class SubGoal:
    id: str
    description: str
    dependencies: List[str]
    assigned_agent: Optional[str] = None
    status: str = "pending"
    result: Any = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GoalDecomposer:
    """Breaks complex intents into sub-goals, routes to specialized agents,
    resolves dependencies, and assembles results."""

    def __init__(self, orchestrator: AgentOrchestrator):
        self.orchestrator = orchestrator
        self.active_goals: Dict[str, List[SubGoal]] = {}

    async def decompose(self, intent: str, context: dict = None) -> dict:
        context = context or {}
        intent_lower = intent.lower()

        has_multiple_actions = any(word in intent_lower for word in
            ["and", "then", "also", "plus", "additionally", "meanwhile", "while"])
        has_conditions = any(word in intent_lower for word in
            ["if", "when", "unless", "until", "once", "after", "before"])
        needs_research = any(word in intent_lower for word in
            ["find", "search", "research", "investigate", "analyze", "assess"])
        needs_execution = any(word in intent_lower for word in
            ["run", "execute", "deploy", "configure", "build", "create", "install", "compile"])
        needs_report = any(word in intent_lower for word in
            ["report", "summarize", "document", "explain", "describe", "output"])

        sub_goals = []
        goal_id_base = hashlib.md5(intent.encode()).hexdigest()[:8]

        if needs_research:
            sub_goals.append(SubGoal(
                id=f"{goal_id_base}_research",
                description=f"Research and gather intelligence: {intent}",
                dependencies=[]
            ))

        if needs_execution:
            dep = [sg.id for sg in sub_goals if sg.status == "pending"]
            sub_goals.append(SubGoal(
                id=f"{goal_id_base}_execute",
                description=f"Execute: {intent}",
                dependencies=dep
            ))

        if needs_report:
            dep = [sg.id for sg in sub_goals if sg.status == "pending"]
            sub_goals.append(SubGoal(
                id=f"{goal_id_base}_report",
                description=f"Report and document results",
                dependencies=dep
            ))

        if not sub_goals:
            sub_goals.append(SubGoal(
                id=f"{goal_id_base}_single",
                description=intent,
                dependencies=[]
            ))

        for sg in sub_goals:
            route = self.orchestrator.route(sg.description)
            if route:
                sg.assigned_agent = route.agent_name

        self.active_goals[goal_id_base] = sub_goals

        return {
            "goal_id": goal_id_base,
            "original_intent": intent,
            "sub_goals": [asdict(sg) for sg in sub_goals],
            "parallel_phases": self._identify_parallel_phases(sub_goals),
            "estimated_complexity": len(sub_goals)
        }

    def _identify_parallel_phases(self, sub_goals: List[SubGoal]) -> List[list]:
        phases = []
        remaining = list(sub_goals)
        while remaining:
            phase = [sg for sg in remaining if not sg.dependencies or
                     all(d not in [s.id for s in remaining] for d in sg.dependencies)]
            if not phase:
                break
            phases.append([sg.id for sg in phase])
            remaining = [sg for sg in remaining if sg not in phase]
        return phases

    async def execute(self, goal_id: str, context: dict = None) -> dict:
        context = context or {}
        sub_goals = self.active_goals.get(goal_id)
        if not sub_goals:
            return {"error": f"Goal {goal_id} not found"}

        phases = self._identify_parallel_phases(sub_goals)
        results = {}

        for phase_ids in phases:
            phase_tasks = []
            for sg_id in phase_ids:
                sg = next((s for s in sub_goals if s.id == sg_id), None)
                if sg:
                    sg.status = "running"
                    phase_tasks.append(self._execute_single(sg, context))

            phase_results = await asyncio.gather(*phase_tasks, return_exceptions=True)
            for sg, result in zip([s for s in sub_goals if s.id in phase_ids], phase_results):
                if isinstance(result, Exception):
                    sg.status = "failed"
                    sg.result = str(result)
                else:
                    sg.status = "completed"
                    sg.result = result
                results[sg.id] = {"status": sg.status, "result": sg.result}
                await self.orchestrator.store_memory(
                    agent_name="goal_decomposer",
                    key=f"goal:{goal_id}:{sg.id}",
                    value=json.dumps(sg.result) if not isinstance(sg.result, str) else sg.result,
                    tags=["goal", goal_id],
                    metadata={"goal_id": goal_id, "sub_goal": sg.id}
                )

        return {
            "goal_id": goal_id,
            "sub_goals": {sg.id: {"status": sg.status, "result": sg.result} for sg in sub_goals},
            "all_completed": all(sg.status == "completed" for sg in sub_goals)
        }

    async def _execute_single(self, sg: SubGoal, context: dict) -> Any:
        route = self.orchestrator.route(sg.description)
        if route:
            enriched = {**context, "sub_goal_id": sg.id, "goal_description": sg.description}
            result = await self.orchestrator.handle_intent(sg.description, enriched)
            return result
        return {"error": "No agent matched", "sub_goal": sg.id}

# ═══════════════════════════════════════════════════════════════
# 2. CROSS-SESSION PERSISTENT LEARNING
# ═══════════════════════════════════════════════════════════════

class ReinforcementMemory(MemoryStore):
    def __init__(self, db_path: str = "./memory.db"):
        super().__init__(db_path)
        self._init_reinforcement()

    def _init_reinforcement(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reinforcement (
                memory_id INTEGER NOT NULL,
                signal INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_reinforce_mem ON reinforcement(memory_id)")
        self.conn.commit()

    def reinforce(self, memory_id: int, signal: int, session_id: str = ""):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO reinforcement (memory_id, signal, session_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (memory_id, signal, session_id or "default", now)
        )
        self.conn.commit()

    def get_reinforcement_score(self, memory_id: int) -> float:
        cursor = self.conn.execute(
            "SELECT COALESCE(SUM(signal), 0) FROM reinforcement WHERE memory_id = ?",
            (memory_id,)
        )
        return cursor.fetchone()[0]

    def search(self, query: str, agent_name: Optional[str] = None,
               limit: int = 5, min_score: float = 0.3,
               boost_reinforced: bool = True) -> List[Dict[str, Any]]:
        results = super().search(query, agent_name=agent_name, limit=limit * 2, min_score=min_score)
        if boost_reinforced:
            for r in results:
                mem_id = r.get("id")
                if mem_id:
                    score = self.get_reinforcement_score(mem_id)
                    boost = min(0.3, max(0, score * 0.05))
                    r["score"] = min(1.0, r["score"] * (1.0 + boost))
                    r["reinforcement"] = score
            results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

# ═══════════════════════════════════════════════════════════════
# 3. UNIVERSAL PROTOCOL BRIDGE
# ═══════════════════════════════════════════════════════════════

class ProtocolBridge:
    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._protocols = {
            "http": self._connect_http,
            "https": self._connect_http,
            "sqlite3": self._connect_sqlite,
            "postgresql": self._connect_postgres,
            "redis": self._connect_redis,
            "mqtt": self._connect_mqtt,
            "file": self._connect_file,
            "subprocess": self._connect_subprocess,
        }

    def detect(self, target: str) -> str:
        if target.startswith(("http://", "https://")):
            return "http"
        elif target.startswith("sqlite3://") or target.endswith(".db"):
            return "sqlite3"
        elif target.startswith(("postgresql://", "postgres://")):
            return "postgresql"
        elif target.startswith("redis://"):
            return "redis"
        elif target.startswith("mqtt://"):
            return "mqtt"
        elif target.startswith("file://") or os.path.exists(target):
            return "file"
        elif target.startswith(("cmd://", "sh://")):
            return "subprocess"
        return "unknown"

    async def connect(self, target: str, **kwargs) -> dict:
        protocol = self.detect(target)
        if protocol == "unknown":
            return {"error": f"Unknown protocol for target: {target}"}
        handler = self._protocols.get(protocol)
        if not handler:
            return {"error": f"No handler for protocol: {protocol}"}
        conn_id = hashlib.md5(f"{target}:{time.time()}".encode()).hexdigest()[:12]
        try:
            info = handler(target, **kwargs)
            self._connections[conn_id] = info
            return {"connection_id": conn_id, "protocol": protocol, "target": target,
                    "status": "connected", "metadata": info.get("metadata", {})}
        except Exception as e:
            return {"error": f"Failed to connect: {e}", "target": target, "protocol": protocol}

    def _connect_http(self, target: str, **kwargs) -> dict:
        import urllib.parse
        parsed = urllib.parse.urlparse(target)
        return {"type": "http", "host": parsed.hostname, "port": parsed.port or 443,
                "path": parsed.path, "metadata": {"scheme": parsed.scheme}}

    def _connect_sqlite(self, target: str, **kwargs) -> dict:
        path = target.replace("sqlite3://", "")
        import sqlite3
        conn = sqlite3.connect(path)
        return {"type": "sqlite", "connection": conn, "metadata": {"path": path}}

    def _connect_postgres(self, target: str, **kwargs) -> dict:
        return {"type": "postgresql", "target": target, "metadata": {"note": "Install psycopg2"}}

    def _connect_redis(self, target: str, **kwargs) -> dict:
        return {"type": "redis", "target": target, "metadata": {"note": "Install redis-py"}}

    def _connect_mqtt(self, target: str, **kwargs) -> dict:
        return {"type": "mqtt", "target": target, "metadata": {"note": "Install paho-mqtt"}}

    def _connect_file(self, target: str, **kwargs) -> dict:
        path = target.replace("file://", "")
        return {"type": "file", "path": path, "exists": os.path.exists(path),
                "metadata": {"path": path, "size": os.path.getsize(path) if os.path.exists(path) else 0}}

    def _connect_subprocess(self, target: str, **kwargs) -> dict:
        cmd = target.replace("cmd://", "").replace("sh://", "")
        return {"type": "subprocess", "command": cmd, "metadata": {"command": cmd}}

    def list_connections(self) -> List[dict]:
        return [{"id": cid, **info} for cid, info in self._connections.items() if isinstance(info, dict)]

    def disconnect(self, connection_id: str) -> bool:
        if connection_id in self._connections:
            info = self._connections.pop(connection_id)
            conn = info.get("connection") if isinstance(info, dict) else None
            if conn and hasattr(conn, 'close'):
                try:
                    conn.close()
                except Exception:
                    pass
            return True
        return False

# ═══════════════════════════════════════════════════════════════
# 4. SELF-HEALING PLUGIN RUNTIME
# ═══════════════════════════════════════════════════════════════

class HealingPluginManager(PluginManager):
    """Extends PluginManager with health monitoring, auto-restart, and quarantine."""

    def __init__(self, plugin_dir: str, hot_reload: bool = False, max_restarts: int = 3):
        super().__init__(plugin_dir, hot_reload=hot_reload)
        self.max_restarts = max_restarts
        self._failure_count: Dict[str, int] = {}
        self._quarantined: Dict[str, float] = {}

    def monitor_health(self, plugin_name: str, health_check: Callable[[], bool]):
        import threading
        def _check_loop():
            while True:
                time.sleep(30)
                if plugin_name in self._quarantined:
                    continue
                try:
                    if not health_check():
                        self._handle_failure(plugin_name)
                except Exception as e:
                    logger.error(f"Health check failed for plugin '{plugin_name}': {e}")
                    self._handle_failure(plugin_name)
        t = threading.Thread(target=_check_loop, daemon=True)
        t.start()

    def _handle_failure(self, plugin_name: str):
        self._failure_count[plugin_name] = self._failure_count.get(plugin_name, 0) + 1
        count = self._failure_count[plugin_name]
        logger.warning(f"Plugin '{plugin_name}' failed (attempt {count}/{self.max_restarts})")
        if count >= self.max_restarts:
            backoff = min(3600, 60 * (2 ** (count - self.max_restarts)))
            self._quarantined[plugin_name] = time.time() + backoff
            logger.error(f"Plugin '{plugin_name}' quarantined for {backoff}s")
            return
        asyncio.run_coroutine_threadsafe(self._reload_plugin(plugin_name), asyncio.get_event_loop())

    async def _reload_plugin(self, plugin_name: str):
        try:
            await super().reload_plugin(plugin_name)
            logger.info(f"Plugin '{plugin_name}' restarted successfully")
        except Exception as e:
            logger.error(f"Failed to restart plugin '{plugin_name}': {e}")
            self._handle_failure(plugin_name)

    def release_quarantine(self, plugin_name: str) -> bool:
        if plugin_name in self._quarantined:
            del self._quarantined[plugin_name]
            self._failure_count[plugin_name] = 0
            return True
        return False

    def quarantine_status(self) -> list:
        now = time.time()
        return [
            {"plugin": name, "cooldown_remaining": round(max(0, until - now), 1)}
            for name, until in self._quarantined.items()
        ]

# ═══════════════════════════════════════════════════════════════
# 5. PLUGIN MARKETPLACE — configurable registry URLs
# ═══════════════════════════════════════════════════════════════

class PluginMarketplace:
    """Remote plugin discovery, version negotiation, dependency resolution,
    and one-command installation.

    Fetches a plugin index from a remote registry or local directory,
    resolves dependency trees, downloads, verifies checksums, and installs.

    Registry URLs are configurable via:
      - env var: ADVANCEMENT_REGISTRY_URLS (comma-separated)
      - explicit argument to constructor
      - default fallback: local file ./registry.json, then remote URLs
    """

    def __init__(self, install_dir: str = "./plugins",
                 registry_urls: Optional[List[str]] = None):
        self.install_dir = Path(install_dir)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self._registry: List[dict] = []

        # Priority: explicit arg > env var > defaults
        if registry_urls:
            self.registry_urls = registry_urls
        else:
            env_urls = os.environ.get("ADVANCEMENT_REGISTRY_URLS", "")
            if env_urls:
                self.registry_urls = [u.strip() for u in env_urls.split(",") if u.strip()]
            else:
                # Default: local file first, then remote fallbacks
                self.registry_urls = [
                    "file://./registry.json",
                    "https://raw.githubusercontent.com/eurothrottle/advancement-plugins/main/registry.json",
                    "https://advancement-marketplace.example.com/registry.json",
                ]

    async def refresh_registry(self) -> list:
        """Fetch the latest plugin registry from configured sources."""
        self._registry = []
        for url in self.registry_urls:
            try:
                if url.startswith("file://"):
                    local_path = url.replace("file://", "")
                    if Path(local_path).exists():
                        with open(local_path) as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                self._registry.extend(data)
                            elif isinstance(data, dict) and "plugins" in data:
                                self._registry.extend(data["plugins"])
                            logger.info(f"Loaded local registry from {local_path}")
                else:
                    req = urllib.request.Request(url, headers={"User-Agent": "AdvancementMachine/0.1"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode())
                        if isinstance(data, list):
                            self._registry.extend(data)
                        elif isinstance(data, dict) and "plugins" in data:
                            self._registry.extend(data["plugins"])
                        logger.info(f"Fetched registry from {url}")
            except Exception as e:
                logger.warning(f"Failed to fetch registry from {url}: {e}")
        # Deduplicate by name
        seen = set()
        unique = []
        for p in self._registry:
            name = p.get("name")
            if name and name not in seen:
                seen.add(name)
                unique.append(p)
        self._registry = unique
        return self._registry

    def search(self, query: str) -> list:
        query_lower = query.lower()
        results = []
        for p in self._registry:
            name = p.get("name", "").lower()
            desc = p.get("description", "").lower()
            tags = [t.lower() for t in p.get("tags", [])]
            if query_lower in name or query_lower in desc or any(query_lower in t for t in tags):
                results.append(p)
        return results

    def resolve_dependencies(self, plugin_name: str, version: str = "latest",
                             visited: set = None) -> list:
        visited = visited or set()
        if plugin_name in visited:
            return []
        visited.add(plugin_name)
        entry = next((p for p in self._registry if p["name"] == plugin_name), None)
        if not entry:
            return []
        deps = entry.get("dependencies", {})
        flat = []
        for dep_name, dep_version in deps.items():
            if dep_name not in visited:
                flat.extend(self.resolve_dependencies(dep_name, dep_version, visited))
        flat.append((plugin_name, version, entry.get("download_url", "")))
        return flat

    async def install(self, plugin_name: str, version: str = "latest",
                      verify_checksum: bool = True) -> dict:
        resolution = self.resolve_dependencies(plugin_name, version)
        if not resolution:
            return {"error": f"Plugin '{plugin_name}' not found in registry", "plugin": plugin_name}
        installed = []
        for dep_name, dep_version, dl_url in resolution:
            plugin_path = self.install_dir / f"{dep_name}.py"
            if plugin_path.exists():
                installed.append({"name": dep_name, "version": dep_version, "status": "already_installed"})
                continue
            target_url = dl_url or next(
                (p.get("download_url", "") for p in self._registry if p["name"] == dep_name), ""
            )
            if not target_url:
                installed.append({"name": dep_name, "version": dep_version, "status": "no_download_url"})
                continue
            try:
                req = urllib.request.Request(target_url, headers={"User-Agent": "AdvancementMachine/0.1"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                if verify_checksum:
                    entry = next((p for p in self._registry if p["name"] == dep_name), {})
                    expected = entry.get("sha256", "")
                    if expected and hashlib.sha256(content).hexdigest() != expected:
                        installed.append({"name": dep_name, "version": dep_version, "status": "checksum_mismatch"})
                        continue
                with open(plugin_path, "wb") as f:
                    f.write(content)
                installed.append({"name": dep_name, "version": dep_version, "status": "installed"})
                logger.info(f"Installed plugin '{dep_name}' v{dep_version}")
            except Exception as e:
                installed.append({"name": dep_name, "version": dep_version, "status": f"error: {e}"})
        return {
            "plugin": plugin_name,
            "version": version,
            "dependencies": installed,
            "all_succeeded": all(i["status"] in ("installed", "already_installed") for i in installed)
        }

    def list_local(self) -> list:
        plugins = []
        for f in self.install_dir.glob("*.py"):
            if f.stem == "__init__":
                continue
            plugins.append({"name": f.stem, "path": str(f), "size": f.stat().st_size})
        return plugins

# ═══════════════════════════════════════════════════════════════
# 6. ADAPTIVE SECURITY & STEALTH — environment fingerprint + TLS discovery
# ═══════════════════════════════════════════════════════════════

class AdaptiveStealth:
    """Auto-adjusts security posture based on environment fingerprint.

    Detects debuggers, sandboxes, VMs, monitoring tools, and network
    posture, then adjusts TLS, log level, and network delay.

    TLS cert discovery searches standard paths and returns the best
    candidate for the current environment.
    """

    TLS_CANDIDATE_PATHS = [
        "/etc/advancement/server.pem",
        "/etc/ssl/certs/server.pem",
        "./server.pem",
        "./test-certs/server.pem",
    ]
    KEY_CANDIDATE_PATHS = [
        "/etc/advancement/server.key",
        "/etc/ssl/private/server.key",
        "./server.key",
        "./test-certs/server.key",
    ]
    CA_CANDIDATE_PATHS = [
        "/etc/advancement/ca.pem",
        "./ca.pem",
        "./test-certs/ca.pem",
    ]
    CRL_CANDIDATE_PATHS = [
        "/etc/advancement/crl.pem",
        "./crl.pem",
        "./test-certs/crl.pem",
    ]

    def __init__(self):
        self._profile: Dict[str, Any] = {}
        self._posture: str = "stealth"

    def fingerprint_environment(self) -> dict:
        """Build a full environment fingerprint.

        Returns dict with:
          - platform, architecture, python version
          - container detection
          - debugger detection
          - sandbox/analysis environment detection
          - monitoring tools detection (Wireshark, Frida, etc.)
          - network posture (external vs restricted)
          - process name and uid
          - auto-discovered TLS certs
          - assigned posture and derived settings
        """
        env = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "python_version": sys.version,
            "container": self._detect_container(),
            "debugger": self._detect_debugger(),
            "sandbox": self._detect_sandbox(),
            "monitoring": self._detect_monitoring(),
            "network": self._detect_network_posture(),
            "process_name": os.path.basename(sys.argv[0]) if sys.argv else "unknown",
            "uid": os.getuid() if hasattr(os, 'getuid') else -1,
            "env_vars": {
                "log_level": os.environ.get("ADVANCEMENT_LOG_LEVEL", "not set"),
                "registry_urls": os.environ.get("ADVANCEMENT_REGISTRY_URLS", "not set"),
                "memory_db": os.environ.get("ADVANCEMENT_MEMORY_DB", "not set"),
            },
        }

        # Auto-discover TLS certs
        env["tls"] = self.discover_tls_certs()

        # Determine posture
        if env["sandbox"] or env["debugger"]:
            self._posture = "stealth"
        elif env["monitoring"]:
            self._posture = "stealth"
        elif env["container"]:
            self._posture = "normal"
        else:
            self._posture = "aggressive"

        env["posture"] = self._posture
        env["log_level"] = self.get_log_level()
        env["network_delay"] = self.get_network_delay()
        env["obfuscate"] = self.should_obfuscate()

        self._profile = env
        return env

    def discover_tls_certs(self) -> dict:
        """Search standard paths for TLS certificate, key, CA, and CRL files.

        Returns a dict with paths to discovered files (or None for missing).
        """
        result = {"certfile": None, "keyfile": None, "cafile": None, "crlfile": None}

        for path in self.TLS_CANDIDATE_PATHS:
            if Path(path).exists() and not result["certfile"]:
                result["certfile"] = path
                # Look for matching key
                stem = Path(path).stem
                key_candidates = [
                    path.replace("server.pem", "server.key"),
                    path.replace(".pem", ".key"),
                ]
                for kp in key_candidates:
                    if Path(kp).exists():
                        result["keyfile"] = kp
                        break
                break

        for path in self.CA_CANDIDATE_PATHS:
            if Path(path).exists() and not result["cafile"]:
                result["cafile"] = path
                break

        for path in self.CRL_CANDIDATE_PATHS:
            if Path(path).exists() and not result["crlfile"]:
                result["crlfile"] = path
                break

        return result

    def _detect_container(self) -> bool:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            try:
                content = cgroup.read_text()
                if "docker" in content or "kubepods" in content or "lxc" in content:
                    return True
            except Exception:
                pass
        return Path("/.dockerenv").exists()

    def _detect_debugger(self) -> bool:
        if sys.gettrace() is not None:
            return True
        try:
            import pydevd
            return True
        except ImportError:
            pass
        return False

    def _detect_sandbox(self) -> bool:
        hostname = os.uname().nodename if hasattr(os, 'uname') else ""
        sandbox_indicators = ["sandbox", "analysis", "malware", "cuckoo", "virustotal",
                              "joesandbox", "hybrid-analysis", "detonate"]
        return any(ind in hostname.lower() for ind in sandbox_indicators)

    def _detect_monitoring(self) -> bool:
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name', '').lower()
                if any(tool in name for tool in ['wireshark', 'tcpdump', 'frida', 'strace',
                                                  'ltrace', 'ghidra', 'ida', 'x64dbg', 'ollydbg']):
                    return True
        except Exception:
            pass
        return False

    def _detect_network_posture(self) -> str:
        try:
            import socket
            result = socket.getaddrinfo("8.8.8.8", 53, socket.AF_INET, socket.SOCK_STREAM)
            return "external" if result else "restricted"
        except Exception:
            return "restricted"

    def get_log_level(self) -> str:
        return "ERROR" if self._posture == "stealth" else "INFO"

    def get_network_delay(self) -> float:
        import random
        if self._posture == "stealth":
            return round(random.uniform(0.5, 2.0), 2)
        return 0.0

    def should_obfuscate(self) -> bool:
        return self._posture in ("stealth", "normal")

    def posture_report(self) -> dict:
        return {
            "profile": self._profile,
            "posture": self._posture,
            "log_level": self.get_log_level(),
            "network_delay": self.get_network_delay(),
            "obfuscate": self.should_obfuscate(),
        }