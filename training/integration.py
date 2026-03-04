# helena_training/integration.py
import git
import shutil
from pathlib import Path

class IntegrationEngine:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.repo = git.Repo.init(project_root)  # ensure git repo exists

    def apply_patch(self, patch: dict[str, any]) -> bool:
        # Create a backup branch
        branch_name = f"pre_{patch['id']}"
        if branch_name not in self.repo.branches:
            self.repo.create_head(branch_name)
        
        # Apply patch to live files (using same method as sandbox, but directly)
        module_path = self.root / patch['module'].replace('.', os.sep) + '.py'
        with open(module_path, 'r') as f:
            old = f.read()
        new_code = self._replace_function(old, patch['function'], patch['new_code'])
        with open(module_path, 'w') as f:
            f.write(new_code)
        
        # Commit change
        self.repo.index.add([str(module_path)])
        self.repo.index.commit(f"Auto-improvement: {patch['description']}")
        return True

    def rollback(self, patch_id: str):
        # Revert to state before patch
        branch = f"pre_{patch_id}"
        if branch in self.repo.branches:
            self.repo.git.checkout(branch)
            # Then maybe merge or just stay on that branch