# helena_core/introspection.py
"""
HELENA Self-Introspection System

Gives HELENA the ability to read, understand, and reason about her
own source code.  This is a core requirement for self-upgrading and
self-teaching capabilities.

Capabilities
------------
* Read any of her own source files.
* Parse Python modules into structured AST representations.
* List all classes, functions, and their docstrings.
* Compute code metrics (lines, complexity, dependency graph).
* Provide a structured "self-model" that the chat engine and
  training pipeline can query.
"""
import ast
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class CodeEntity:
    """Represents a class, function, or module found during introspection."""
    __slots__ = (
        "name", "kind", "module_path", "lineno", "end_lineno",
        "docstring", "parameters", "decorators", "bases", "children",
    )

    def __init__(self, name: str, kind: str, module_path: str,
                 lineno: int = 0, end_lineno: int = 0,
                 docstring: str = "", parameters: Optional[List[str]] = None,
                 decorators: Optional[List[str]] = None,
                 bases: Optional[List[str]] = None) -> None:
        self.name = name
        self.kind = kind              # "module", "class", "function", "method"
        self.module_path = module_path
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.docstring = docstring
        self.parameters = parameters or []
        self.decorators = decorators or []
        self.bases = bases or []
        self.children: List["CodeEntity"] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "module": self.module_path,
            "line": self.lineno,
            "end_line": self.end_lineno,
            "docstring": self.docstring[:200] if self.docstring else "",
            "parameters": self.parameters,
            "decorators": self.decorators,
            "bases": self.bases,
            "children": [c.to_dict() for c in self.children],
        }


class SelfIntrospector:
    """
    Allows HELENA to read and understand her own codebase.

    Usage::

        intro = SelfIntrospector()
        intro.scan()
        modules = intro.list_modules()
        classes = intro.list_classes()
        source  = intro.read_file("helena_core/kernel/core.py")
    """

    def __init__(self, root: Optional[str] = None) -> None:
        if root is None:
            # Default: the HELENA project root (parent of helena_core)
            root = str(Path(__file__).resolve().parent.parent)
        self.root = Path(root)
        self._entities: Dict[str, CodeEntity] = {}  # module_path -> entity
        self._all_classes: List[CodeEntity] = []
        self._all_functions: List[CodeEntity] = []
        self._dependency_map: Dict[str, List[str]] = defaultdict(list)
        self._scanned = False

    # ── Scanning ──────────────────────────────────────────────────

    def scan(self) -> Dict[str, Any]:
        """Scan the entire codebase and build the self-model."""
        self._entities.clear()
        self._all_classes.clear()
        self._all_functions.clear()
        self._dependency_map.clear()

        py_files = list(self.root.rglob("*.py"))
        # Exclude __pycache__, .git, venv
        py_files = [
            f for f in py_files
            if "__pycache__" not in str(f)
            and ".git" not in str(f)
            and "venv" not in str(f)
        ]

        for filepath in py_files:
            rel = str(filepath.relative_to(self.root))
            try:
                self._parse_file(filepath, rel)
            except Exception as exc:
                logger.debug("Introspection: failed to parse %s: %s", rel, exc)

        self._scanned = True
        return self.get_summary()

    def _parse_file(self, filepath: Path, rel_path: str) -> None:
        """Parse a single Python file into entities."""
        source = filepath.read_text(errors="replace")
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            return

        module_entity = CodeEntity(
            name=rel_path,
            kind="module",
            module_path=rel_path,
            lineno=1,
            end_lineno=len(source.splitlines()),
            docstring=ast.get_docstring(tree) or "",
        )

        # Extract imports for dependency map
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._dependency_map[rel_path].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._dependency_map[rel_path].append(node.module)

        # Extract top-level classes and functions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls_entity = self._parse_class(node, rel_path)
                module_entity.children.append(cls_entity)
                self._all_classes.append(cls_entity)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_entity = self._parse_function(node, rel_path)
                module_entity.children.append(func_entity)
                self._all_functions.append(func_entity)

        self._entities[rel_path] = module_entity

    def _parse_class(self, node: ast.ClassDef, module: str) -> CodeEntity:
        entity = CodeEntity(
            name=node.name,
            kind="class",
            module_path=module,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node) or "",
            decorators=[self._decorator_name(d) for d in node.decorator_list],
            bases=[self._node_name(b) for b in node.bases],
        )
        # Methods
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = self._parse_function(child, module, kind="method")
                entity.children.append(method)
                self._all_functions.append(method)
        return entity

    def _parse_function(self, node, module: str,
                        kind: str = "function") -> CodeEntity:
        params: List[str] = []
        for arg in node.args.args:
            params.append(arg.arg)
        return CodeEntity(
            name=node.name,
            kind=kind,
            module_path=module,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node) or "",
            parameters=params,
            decorators=[self._decorator_name(d) for d in node.decorator_list],
        )

    @staticmethod
    def _decorator_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            if isinstance(node.func, ast.Attribute):
                return node.func.attr
        return "<unknown>"

    @staticmethod
    def _node_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return "<unknown>"

    # ── Queries ───────────────────────────────────────────────────

    def read_file(self, rel_path: str) -> Optional[str]:
        """Read the source of any file in the HELENA codebase."""
        full = self.root / rel_path
        if full.exists() and full.is_file():
            return full.read_text(errors="replace")
        return None

    def list_modules(self) -> List[str]:
        """Return all scanned module paths."""
        if not self._scanned:
            self.scan()
        return sorted(self._entities.keys())

    def list_classes(self) -> List[Dict[str, Any]]:
        """Return all classes found."""
        if not self._scanned:
            self.scan()
        return [c.to_dict() for c in self._all_classes]

    def list_functions(self, module: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all functions, optionally filtered by module."""
        if not self._scanned:
            self.scan()
        funcs = self._all_functions
        if module:
            funcs = [f for f in funcs if f.module_path == module]
        return [f.to_dict() for f in funcs]

    def get_module_info(self, rel_path: str) -> Optional[Dict[str, Any]]:
        """Get structured info for a single module."""
        if not self._scanned:
            self.scan()
        entity = self._entities.get(rel_path)
        return entity.to_dict() if entity else None

    def get_dependencies(self, rel_path: str) -> List[str]:
        """Return import dependencies for a module."""
        if not self._scanned:
            self.scan()
        return self._dependency_map.get(rel_path, [])

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search across all entities by name or docstring."""
        if not self._scanned:
            self.scan()
        q = query.lower()
        results: List[Dict[str, Any]] = []
        for entity in self._all_classes + self._all_functions:
            searchable = f"{entity.name} {entity.docstring}".lower()
            if q in searchable:
                results.append(entity.to_dict())
                if len(results) >= limit:
                    break
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Return a high-level summary of the codebase."""
        total_lines = 0
        for entity in self._entities.values():
            total_lines += entity.end_lineno
        return {
            "modules": len(self._entities),
            "classes": len(self._all_classes),
            "functions": len(self._all_functions),
            "total_lines": total_lines,
            "dependencies": {k: len(v) for k, v in self._dependency_map.items()},
        }
