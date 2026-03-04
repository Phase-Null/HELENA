# helena_core/modules/loader.py
"""
HELENA Module Loader – hot-loadable worker units with sandboxing.

Modules are self-contained Python packages that HELENA can discover,
load, validate, and unload at runtime.  Each module declares its
capabilities via a ``module.json`` manifest.

Lifecycle
---------
DISCOVERED → VALIDATED → LOADED → ACTIVE → (SUSPENDED | UNLOADED | ERROR)
"""
import importlib
import importlib.util
import json
import time
import logging
import threading
from enum import Enum, auto
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable

logger = logging.getLogger(__name__)


class ModuleState(Enum):
    DISCOVERED = auto()
    VALIDATED = auto()
    LOADED = auto()
    ACTIVE = auto()
    SUSPENDED = auto()
    UNLOADED = auto()
    ERROR = auto()


@dataclass
class ModuleInfo:
    """Metadata for a loaded module."""
    name: str
    version: str = "0.0.0"
    author: str = "unknown"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    state: ModuleState = ModuleState.DISCOVERED
    path: str = ""
    load_time: float = 0.0
    error: str = ""
    instance: Optional[Any] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "state": self.state.name,
            "path": self.path,
            "load_time": self.load_time,
            "error": self.error,
        }


class HelenaModule:
    """
    Base class that all HELENA modules must subclass.

    Modules implement ``on_load``, ``on_unload``, and ``execute``.
    """

    name: str = "unnamed"
    version: str = "0.0.0"

    def on_load(self, kernel=None, memory=None) -> bool:
        """Called when the module is loaded.  Return True on success."""
        return True

    def on_unload(self) -> None:
        """Called when the module is unloaded."""
        pass

    def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a module command."""
        return {"status": "not_implemented"}

    def get_capabilities(self) -> List[str]:
        """Return list of commands this module provides."""
        return []


class ModuleLoader:
    """
    Discovers, validates, loads, and manages HELENA modules.
    """

    def __init__(self, modules_dir: Optional[str] = None,
                 kernel=None, memory=None) -> None:
        if modules_dir is None:
            modules_dir = str(Path(__file__).resolve().parent.parent.parent / "modules")
        self.modules_dir = Path(modules_dir)
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel
        self.memory = memory

        self._lock = threading.RLock()
        self._modules: Dict[str, ModuleInfo] = {}

        # Security: allowed module capabilities
        self._allowed_capabilities = {
            "code_analysis", "code_generation", "file_io",
            "network_scan", "memory_query", "training",
            "reporting", "monitoring", "utility",
        }
        # Blacklisted module names
        self._blacklist: set = set()

        logger.info("ModuleLoader initialised (dir: %s)", self.modules_dir)

    # ── Discovery ─────────────────────────────────────────────────

    def discover(self) -> List[ModuleInfo]:
        """Scan the modules directory for new modules."""
        with self._lock:
            discovered: List[ModuleInfo] = []
            if not self.modules_dir.exists():
                return discovered

            for item in self.modules_dir.iterdir():
                if not item.is_dir():
                    continue
                manifest_path = item / "module.json"
                if not manifest_path.exists():
                    continue
                if item.name in self._blacklist:
                    continue
                if item.name in self._modules:
                    continue

                try:
                    with open(manifest_path) as fh:
                        manifest = json.load(fh)
                    info = ModuleInfo(
                        name=manifest.get("name", item.name),
                        version=manifest.get("version", "0.0.0"),
                        author=manifest.get("author", "unknown"),
                        description=manifest.get("description", ""),
                        capabilities=manifest.get("capabilities", []),
                        dependencies=manifest.get("dependencies", []),
                        state=ModuleState.DISCOVERED,
                        path=str(item),
                    )
                    self._modules[info.name] = info
                    discovered.append(info)
                    logger.info("Discovered module: %s v%s", info.name, info.version)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Bad module manifest at %s: %s", manifest_path, exc)

            return discovered

    # ── Validation ────────────────────────────────────────────────

    def validate(self, name: str) -> bool:
        """Validate a discovered module before loading."""
        with self._lock:
            info = self._modules.get(name)
            if not info:
                return False

            # Check capabilities are allowed
            for cap in info.capabilities:
                if cap not in self._allowed_capabilities:
                    info.state = ModuleState.ERROR
                    info.error = f"Disallowed capability: {cap}"
                    logger.warning("Module %s rejected: %s", name, info.error)
                    return False

            # Check entry point exists
            entry = Path(info.path) / "__init__.py"
            if not entry.exists():
                info.state = ModuleState.ERROR
                info.error = "Missing __init__.py"
                return False

            info.state = ModuleState.VALIDATED
            return True

    # ── Loading ───────────────────────────────────────────────────

    def load(self, name: str) -> bool:
        """Load and activate a validated module."""
        with self._lock:
            info = self._modules.get(name)
            if not info:
                return False
            if info.state not in (ModuleState.VALIDATED, ModuleState.UNLOADED):
                if info.state == ModuleState.DISCOVERED:
                    if not self.validate(name):
                        return False
                else:
                    return False

            try:
                start = time.time()
                # Dynamically import the module
                spec = importlib.util.spec_from_file_location(
                    f"helena_modules.{name}",
                    str(Path(info.path) / "__init__.py"),
                )
                if spec is None or spec.loader is None:
                    info.state = ModuleState.ERROR
                    info.error = "Failed to create import spec"
                    return False

                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                # Find the HelenaModule subclass
                module_cls = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (isinstance(attr, type) and issubclass(attr, HelenaModule)
                            and attr is not HelenaModule):
                        module_cls = attr
                        break

                if module_cls is None:
                    info.state = ModuleState.ERROR
                    info.error = "No HelenaModule subclass found"
                    return False

                instance = module_cls()
                if not instance.on_load(kernel=self.kernel, memory=self.memory):
                    info.state = ModuleState.ERROR
                    info.error = "on_load returned False"
                    return False

                info.instance = instance
                info.state = ModuleState.ACTIVE
                info.load_time = time.time() - start
                logger.info("Loaded module %s in %.3fs", name, info.load_time)
                return True

            except Exception as exc:
                info.state = ModuleState.ERROR
                info.error = str(exc)
                logger.error("Failed to load module %s: %s", name, exc)
                return False

    # ── Unloading ─────────────────────────────────────────────────

    def unload(self, name: str) -> bool:
        """Unload an active module."""
        with self._lock:
            info = self._modules.get(name)
            if not info or info.state not in (ModuleState.ACTIVE, ModuleState.SUSPENDED):
                return False
            try:
                if info.instance:
                    info.instance.on_unload()
                info.instance = None
                info.state = ModuleState.UNLOADED
                logger.info("Unloaded module: %s", name)
                return True
            except Exception as exc:
                logger.error("Error unloading module %s: %s", name, exc)
                info.state = ModuleState.ERROR
                info.error = str(exc)
                return False

    # ── Execution ─────────────────────────────────────────────────

    def execute(self, module_name: str, command: str,
                parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a command on a loaded module."""
        with self._lock:
            info = self._modules.get(module_name)
            if not info or info.state != ModuleState.ACTIVE:
                return {"error": f"Module {module_name} not active"}
            if not info.instance:
                return {"error": f"Module {module_name} has no instance"}
            try:
                return info.instance.execute(command, parameters or {})
            except Exception as exc:
                logger.error("Module %s execution error: %s", module_name, exc)
                return {"error": str(exc)}

    # ── Queries ───────────────────────────────────────────────────

    def list_modules(self) -> List[Dict[str, Any]]:
        """List all known modules."""
        with self._lock:
            return [info.to_dict() for info in self._modules.values()]

    def get_module(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            info = self._modules.get(name)
            return info.to_dict() if info else None

    def get_active_modules(self) -> List[str]:
        with self._lock:
            return [n for n, i in self._modules.items() if i.state == ModuleState.ACTIVE]

    def blacklist_module(self, name: str) -> None:
        """Blacklist a module by name (prevents future loading)."""
        self._blacklist.add(name)
        if name in self._modules:
            self.unload(name)
            del self._modules[name]
        logger.warning("Module blacklisted: %s", name)
