# helena_training/safety.py
class SafetyGovernor:
    def __init__(self, config):
        self.forbidden_modules = {'helena_core.security', 'helena_core.kill_switch'}
        self.max_lines_change = 50

    def approve_patch(self, patch: Dict[str, Any]) -> bool:
        module = patch.get('module', '')
        if any(module.startswith(f) for f in self.forbidden_modules):
            return False
        # More checks: AST analysis for dangerous patterns (eval, exec, etc.)
        return True