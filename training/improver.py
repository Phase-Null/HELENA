# helena_training/improver.py
import random
import time
from typing import List, Dict, Any

class ImprovementGenerator:
    def __init__(self, code_model, dataset, kernel):
        self.code = code_model
        self.data = dataset
        self.kernel = kernel

    def generate_proposals(self, focus_areas: List[str]) -> List[Dict[str, Any]]:
        proposals = []
        # Example: improve error handling in a frequently failing function
        error_patterns = self.data.get_recent('error_patterns', 100)
        if error_patterns:
            # Find the most common error and the function where it occurs
            from collections import Counter
            func_counter = Counter()
            for e in error_patterns:
                func = e.get('function', 'unknown')
                func_counter[func] += 1
            if func_counter:
                worst_func, count = func_counter.most_common(1)[0]
                if count > 10:
                    # Propose adding a try-except or better validation
                    func_node = self.code.get_function('helena_core.kernel.core', worst_func)
                    if func_node:
                        # Generate a patch that adds a try-except around the risky section
                        patch = {
                            'id': f"improve_{worst_func}_{int(time.time())}",
                            'type': 'error_handling',
                            'module': 'helena_core.kernel.core',
                            'function': worst_func,
                            'description': f"Add better error handling in {worst_func}",
                            'new_code': self._add_try_except(func_node),  # would generate code
                            'expected_impact': 0.3,
                        }
                        proposals.append(patch)
        return proposals

    def _add_try_except(self, func_node):
        """Generate new source with try-except around the function body."""
        # This is a complex transformation; in production we'd manipulate AST.
        # For illustration, we return a placeholder.
        return "def " + func_node.name + "(...):\n    try:\n        ...\n    except Exception as e:\n        log_error(e)"