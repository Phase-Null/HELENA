#!/usr/bin/env python3
"""
HELENA fix verification — run from the HELENA root folder.
Expected output: all lines show [OK]
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# ── 1. Logging ───────────────────────────────────────────────────────────────
from helena_core.utils.logging import init_logging
init_logging("./logs")
print("[OK] Logging initialised")

# ── 2. Config ────────────────────────────────────────────────────────────────
from helena_core.utils.config_manager import get_config_manager
config = get_config_manager(Path.home() / ".helena" / "config.yaml")
config.initialize("test_operator")
print("[OK] Config loaded")

# ── 3. Kernel boots without errors ───────────────────────────────────────────
from helena_core.kernel.core import HELENAKernel
kernel = HELENAKernel("test_operator", config)
ok = kernel.initialize()
print(f"[{'OK' if ok else 'FAIL'}] Kernel.initialize()")

# ── 4. LLM loaded (Fix 1) ────────────────────────────────────────────────────
llm_type = type(kernel.llm).__name__ if kernel.llm else None
print(f"[{'OK' if kernel.llm else 'MISS'}] LLM backend: {llm_type or 'None — install Ollama or add .gguf to models/'}")

# ── 5. "chat" in permission matrix (Fix 2) ───────────────────────────────────
from helena_core.kernel.modes import OperationalMode
perms = kernel.permission_manager.get_available_commands(OperationalMode.ENGINEERING, "operator")
print(f"[{'OK' if 'chat' in perms else 'FAIL — Fix 2 not applied'}] chat in permission matrix")

# ── 6. Submit a chat task and get a response (Fixes 2 + 3) ───────────────────
task_id = kernel.submit_task("chat", {"message": "hello"}, source="operator")
if not task_id:
    print("[FAIL] Task submission returned None — check Fix 2")
else:
    time.sleep(3.0)
    status = kernel.get_task_status(task_id)
    result = status.get("result", {}) if status else {}
    error  = result.get("error") if isinstance(result, dict) else None
    output = result.get("result") or result.get("output") if isinstance(result, dict) else None
    if error:
        print(f"[FAIL] Task error: {error}")
    elif output:
        print(f"[OK] Response received: {str(output)[:80]}")
    else:
        print(f"[FAIL] No output — status was: {status}")

# ── 7. Personality configured (Fixes 4 + 5) ──────────────────────────────────
try:
    pe = kernel.personality_engine
    ok = hasattr(pe, "profile") and pe.profile.verbosity > 0
    print(f"[{'OK' if ok else 'FAIL'}] PersonalityEngine configured (verbosity={pe.profile.verbosity})")
except Exception as e:
    print(f"[FAIL] PersonalityEngine: {e}")

# ── 8. Gaming threshold reachable (Fix 6) ────────────────────────────────────
import importlib, inspect
gaming_src = inspect.getsource(importlib.import_module("helena_core.runtime.gaming"))
thresh_ok = "'confidence_threshold': 0.35" in gaming_src or '"confidence_threshold": 0.35' in gaming_src
print(f"[{'OK' if thresh_ok else 'FAIL — Fix 6 not applied'}] Gaming threshold = 0.35 in source")

kernel.shutdown(graceful=False)
print("")
print("Done. Any [FAIL] above = that fix was not saved correctly.")
print("Any [MISS] is informational — not a blocker.")
