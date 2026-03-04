"""
Improvement generator – proposes real code changes based on patterns.
"""
import time
import random
from typing import List, Dict, Any

from helena_core.utils.logging import get_logger

logger = get_logger()

class ImprovementGenerator:
    def __init__(self, code_model, dataset, kernel):
        self.code = code_model
        self.data = dataset
        self.kernel = kernel

    def generate_proposals(self, focus_areas: List[str]) -> List[Dict[str, Any]]:
        proposals = []
        # 1. Fix missing parameters (from structural patterns)
        missing_param_patterns = self.data.get_recent('error_patterns', 100)
        if missing_param_patterns:
            # Count which functions are most affected
            func_counter = {}
            for p in missing_param_patterns:
                if p.get('type') == 'missing_parameter':
                    func = p.get('command', 'unknown')
                    func_counter[func] = func_counter.get(func, 0) + 1
            if func_counter:
                worst_func, count = max(func_counter.items(), key=lambda x: x[1])
                if count > 5:
                    # Propose adding validation
                    patch = {
                        'id': f"validate_{worst_func}_{int(time.time())}",
                        'type': 'input_validation',
                        'module': 'helena_core.kernel.core',  # adjust as needed
                        'function': worst_func,
                        'description': f"Add parameter validation to {worst_func}",
                        'new_code': self._generate_validation_code(worst_func),
                        'expected_impact': 0.2,
                        'security_risk': 'low',
                    }
                    proposals.append(patch)

        # 2. Improve cache sizes based on memory access patterns
        memory_stats = self.data.get_recent('performance_metrics', 50)
        if memory_stats:
            avg_cache_hits = sum(m.get('cache_hits', 0) for m in memory_stats) / len(memory_stats)
            if avg_cache_hits > 100:  # arbitrary threshold
                patch = {
                    'id': f"cache_increase_{int(time.time())}",
                    'type': 'cache_resize',
                    'module': 'helena_core.memory.vector_store',
                    'description': "Increase vector store cache size",
                    'new_code': self._increase_cache_code(),
                    'expected_impact': 0.15,
                    'security_risk': 'low',
                }
                proposals.append(patch)

        # 3. Tweak confidence thresholds based on recent accuracy
        task_history = self.data.get_recent('kernel_tasks', 200)
        if len(task_history) > 50:
            successes = [t for t in task_history if t.get('result', {}).get('status') == 'COMPLETED']
            accuracy = len(successes) / len(task_history)
            if accuracy < 0.8:  # below 80%
                patch = {
                    'id': f"confidence_adjust_{int(time.time())}",
                    'type': 'threshold_tweak',
                    'module': 'helena_core.kernel.validation',
                    'description': "Lower confidence threshold to improve success rate",
                    'new_code': self._adjust_threshold_code(accuracy),
                    'expected_impact': 0.1,
                    'security_risk': 'low',
                }
                proposals.append(patch)

        return proposals

    def _generate_validation_code(self, func_name):
        # In a real system, you'd use AST manipulation.
        # Here we return a dummy code string that the sandbox will test.
        return f"""
def {func_name}(*args, **kwargs):
    # Auto-added validation
    if not args and not kwargs:
        raise ValueError("Missing required parameters")
    # ... original code would follow
        """

    def _increase_cache_code(self):
        return """
# In VectorStore.__init__, increase maxsize
self.cache = LRUCache(maxsize=2000)  # was 1000
"""

    def _adjust_threshold_code(self, accuracy):
        new_thresh = max(0.5, accuracy - 0.1)
        return f"""
# In ValidationChain.validate, lower threshold
similarity_threshold = {new_thresh:.2f}  # was 0.7
"""
