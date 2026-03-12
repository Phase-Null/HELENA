"""
HELENA Code Editor — gives HELENA the ability to read and write her own source files.

Read operations use SelfIntrospector for structured access.
Write operations create .bak backups and validate syntax before committing.
All paths are relative to the HELENA project root.
"""
import ast
import os
import shutil
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from helena_core.utils.logging import get_logger

logger = get_logger()


class CodeEditor:
    """
    Safe read/write access to HELENA's own source files.

    Write operations:
    - Create a .bak backup of the original file
    - Validate Python syntax before writing
    - Refuse to write if syntax check fails
    - Log all write operations

    Read operations delegate to SelfIntrospector where possible.
    """

    # Directories HELENA is allowed to edit
    EDITABLE_DIRS = (
        "helena_ml",
        "helena_core",
        "helena_training",
        "helena_desktop",
    )

    # Files that are never editable
    PROTECTED_FILES = (
        "helena_core/kernel/core.py",      # kernel — too dangerous
        "helena_core/security/kill_switch.py",
        "start_helena.py",
    )

    def __init__(self, root: Optional[str] = None) -> None:
        if root is None:
            root = str(Path(__file__).resolve().parent.parent)
        self.root = Path(root).resolve()

        # Wire in SelfIntrospector for read operations
        try:
            from helena_core.introspection import SelfIntrospector
            self.introspector = SelfIntrospector(root=str(self.root))
            self.introspector.scan()
            logger.info("CodeEditor", f"Introspector scanned {self.root}")
        except Exception as e:
            logger.warning("CodeEditor", f"Introspector unavailable: {e}")
            self.introspector = None

        logger.info("CodeEditor", f"CodeEditor ready — root: {self.root}")

    # ── Read operations ───────────────────────────────────────────

    def read_file(self, relative_path: str) -> Dict[str, Any]:
        """Read a source file and return its content with metadata."""
        path = self._resolve(relative_path)
        if path is None:
            return {"ok": False, "error": f"Path not found or not allowed: {relative_path}"}
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            return {
                "ok": True,
                "path": relative_path,
                "content": content,
                "lines": len(lines),
                "size": len(content),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_files(self, subdir: str = "") -> Dict[str, Any]:
        """List all Python files under a subdirectory."""
        base = self.root / subdir if subdir else self.root
        if not base.exists():
            return {"ok": False, "error": f"Directory not found: {subdir}"}
        files = []
        for p in sorted(base.rglob("*.py")):
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            files.append(rel)
        return {"ok": True, "files": files, "count": len(files)}

    def search_code(self, query: str, subdir: str = "") -> Dict[str, Any]:
        """Search for a string across all Python files."""
        base = self.root / subdir if subdir else self.root
        matches = []
        for p in sorted(base.rglob("*.py")):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                for i, line in enumerate(lines, start=1):
                    if query.lower() in line.lower():
                        rel = str(p.relative_to(self.root)).replace("\\", "/")
                        matches.append({
                            "file": rel,
                            "line": i,
                            "text": line.strip(),
                        })
            except Exception:
                continue
        return {"ok": True, "query": query, "matches": matches, "count": len(matches)}

    def get_structure(self, relative_path: str) -> Dict[str, Any]:
        """Return classes and functions in a file via SelfIntrospector."""
        if self.introspector:
            try:
                entity = self.introspector.get_module(relative_path)
                if entity:
                    return {"ok": True, "structure": entity.to_dict()}
            except Exception:
                pass
        # Fallback: parse with ast directly
        result = self.read_file(relative_path)
        if not result["ok"]:
            return result
        try:
            tree = ast.parse(result["content"])
            structure = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    structure.append({
                        "name": node.name,
                        "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                        "line": node.lineno,
                    })
            return {"ok": True, "path": relative_path, "structure": structure}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Write operations ──────────────────────────────────────────

    def write_file(self, relative_path: str, content: str,
                   reason: str = "") -> Dict[str, Any]:
        """
        Write content to a file.

        Steps:
        1. Check the path is allowed
        2. Validate Python syntax
        3. Back up the original to .bak
        4. Write the new content
        5. Log the operation
        """
        path = self._resolve(relative_path, for_write=True)
        if path is None:
            return {"ok": False, "error": f"Write not allowed: {relative_path}"}

        # Syntax check
        if relative_path.endswith(".py"):
            syntax_ok, syntax_err = self._check_syntax(content)
            if not syntax_ok:
                return {"ok": False, "error": f"Syntax error — write aborted: {syntax_err}"}

        # Backup
        backup_path = None
        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
            logger.info("CodeEditor", f"Backup created: {backup_path.name}")

        # Write
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.info("CodeEditor",
                        f"Wrote {relative_path} ({len(content)} bytes) — {reason or 'no reason given'}")
            # Rescan introspector
            if self.introspector:
                try:
                    self.introspector.scan()
                except Exception:
                    pass
            return {
                "ok": True,
                "path": relative_path,
                "bytes_written": len(content),
                "backup": str(backup_path) if backup_path else None,
            }
        except Exception as e:
            # Restore backup if write failed
            if backup_path and backup_path.exists():
                shutil.copy2(backup_path, path)
                logger.warning("CodeEditor", f"Write failed, restored backup: {e}")
            return {"ok": False, "error": str(e)}

    def restore_backup(self, relative_path: str) -> Dict[str, Any]:
        """Restore a file from its .bak backup."""
        path = self._resolve(relative_path, for_write=True)
        if path is None:
            return {"ok": False, "error": f"Not allowed: {relative_path}"}
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            return {"ok": False, "error": "No backup found"}
        shutil.copy2(backup, path)
        logger.info("CodeEditor", f"Restored {relative_path} from backup")
        return {"ok": True, "path": relative_path}

    # ── Internal helpers ──────────────────────────────────────────

    def _resolve(self, relative_path: str,
                 for_write: bool = False) -> Optional[Path]:
        """Resolve and validate a relative path."""
        # Normalise separators
        relative_path = relative_path.replace("\\", "/").lstrip("/")
        path = (self.root / relative_path).resolve()

        # Must be inside root
        try:
            path.relative_to(self.root)
        except ValueError:
            logger.warning("CodeEditor", f"Path escape attempt: {relative_path}")
            return None

        if for_write:
            # Protected files
            for pf in self.PROTECTED_FILES:
                if relative_path == pf:
                    logger.warning("CodeEditor", f"Write blocked — protected: {relative_path}")
                    return None
            # Must be in an editable directory
            top = relative_path.split("/")[0]
            if top not in self.EDITABLE_DIRS:
                logger.warning("CodeEditor", f"Write blocked — not in editable dir: {relative_path}")
                return None

        return path

    def _check_syntax(self, source: str) -> tuple[bool, str]:
        """Return (True, '') if syntax is valid, (False, error_msg) otherwise."""
        try:
            ast.parse(source)
            return True, ""
        except SyntaxError as e:
            return False, f"line {e.lineno}: {e.msg}"
