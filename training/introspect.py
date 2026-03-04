# helena_training/introspect.py
import ast
import inspect
import importlib
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

class CodeModel:
    """Represents HELENA's own source code."""
    
    def __init__(self, project_root: Path):
        self.root = project_root
        self.modules = {}  # name -> AST

    def load_all(self):
        """Load all Python files under project root."""
        for pyfile in self.root.rglob("*.py"):
            rel_path = pyfile.relative_to(self.root)
            module_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
            with open(pyfile, 'r', encoding='utf-8') as f:
                source = f.read()
            try:
                tree = ast.parse(source)
                self.modules[module_name] = {
                    'path': pyfile,
                    'source': source,
                    'ast': tree
                }
            except SyntaxError as e:
                print(f"Syntax error in {module_name}: {e}")

    def get_function(self, module_name: str, function_name: str) -> Optional[ast.FunctionDef]:
        """Retrieve AST node of a function."""
        module = self.modules.get(module_name)
        if not module:
            return None
        for node in ast.walk(module['ast']):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return node
        return None

    def apply_patch(self, patch: Dict[str, Any]) -> bool:
        """
        Apply a code patch (list of changes).
        Patch format: {
            'module': 'helena_core.kernel.core',
            'type': 'replace_function',
            'function': 'process_request',
            'new_code': '...'   # new source of the function
        }
        """
        # In production, we'd use a library like `astor` to unparse and write.
        # For now, we'll just simulate.
        print(f"Applying patch to {patch['module']}.{patch.get('function','')}")
        # Here we would write the file after validation.
        return True