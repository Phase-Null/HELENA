# helena_training/sandbox.py
import subprocess
import tempfile
import os
import time
from pathlib import Path
import sys

class Sandbox:
    def __init__(self, project_root: Path):
        self.root = project_root

    def test_patch(self, patch: dict[str, any]) -> dict[str, any]:
        """
        Apply patch to a copy of the codebase, run tests, return results.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy project to temp dir
            dest = Path(tmpdir) / "helena"
            self._copy_project(dest)
            
            # Apply patch to the copied file
            module_path = dest / patch['module'].replace('.', os.sep) + '.py'
            with open(module_path, 'r') as f:
                old = f.read()
            # Replace function (very crude – in production use AST-based replacement)
            new_code = self._replace_function(old, patch['function'], patch['new_code'])
            with open(module_path, 'w') as f:
                f.write(new_code)
            
            # Run unit tests in the sandbox
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/"],
                cwd=dest,
                capture_output=True,
                timeout=30,
                env={**os.environ, "PYTHONPATH": str(dest)}
            )
            passed = result.returncode == 0
            return {
                'passed': passed,
                'stdout': result.stdout.decode(),
                'stderr': result.stderr.decode(),
                'performance': self._measure_performance(dest)  # would run benchmarks
            }

    def _copy_project(self, dest):
        # Use shutil.copytree
        import shutil
        shutil.copytree(self.root, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    def _replace_function(self, source, func_name, new_code):
        # Very naive – in reality use AST
        import re
        pattern = rf"def {func_name}\(.*?\):.*?(?=\ndef |\Z)"
        return re.sub(pattern, new_code, source, flags=re.DOTALL)

    def _measure_performance(self, codebase):
        # Run a set of benchmark tasks and return metrics
        return {'speed': 0.95, 'memory': 0.98}  # placeholder