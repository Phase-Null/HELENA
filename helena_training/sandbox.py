"""
Sandbox tester – runs tests and benchmarks.
"""
import subprocess
import tempfile
import shutil
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

from helena_core.utils.logging import get_logger

logger = get_logger()

class Sandbox:
    def __init__(self, project_root: Path):
        self.root = project_root

    def test_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply patch to a copy of the codebase, run tests, measure performance.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy project to temp dir
            dest = Path(tmpdir) / "helena"
            self._copy_project(dest)

            # Apply patch to the copied file
            module_path = dest / patch['module'].replace('.', os.sep) + '.py'
            with open(module_path, 'r') as f:
                old = f.read()
            new_code = self._replace_function(old, patch.get('function'), patch['new_code'])
            with open(module_path, 'w') as f:
                f.write(new_code)

            # Run unit tests
            test_result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-v"],
                cwd=dest,
                capture_output=True,
                timeout=60,
                env={**os.environ, "PYTHONPATH": str(dest)}
            )
            tests_passed = test_result.returncode == 0

            # Run a simple benchmark (if tests passed)
            perf_before = None
            perf_after = None
            if tests_passed:
                perf_before = self._measure_performance(self.root)   # original
                perf_after  = self._measure_performance(dest)        # patched

            return {
                'passed': tests_passed,
                'stdout': test_result.stdout.decode(),
                'stderr': test_result.stderr.decode(),
                'performance_before': perf_before,
                'performance_after': perf_after,
            }

    def _copy_project(self, dest):
        shutil.copytree(self.root, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))

    def _replace_function(self, source, func_name, new_code):
        if not func_name:
            return new_code  # whole file replacement
        import re
        pattern = rf"def {func_name}\(.*?\):.*?(?=\ndef |\Z)"
        return re.sub(pattern, new_code, source, flags=re.DOTALL)

    def _measure_performance(self, codebase):
        """Run a quick benchmark: time a few standard tasks."""
        # In a real system, you'd run actual performance tests.
        # Here we just return a dummy value.
        return {'response_time_ms': 150, 'memory_mb': 256}
