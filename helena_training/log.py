"""
Improvement logging and tracking
"""
import json
from pathlib import Path
from typing import Dict, Any, List

class ImprovementLog:
    def __init__(self, log_path: str):
        self.log_path = Path(log_path).expanduser()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logs = []
    
    def log_improvement(self, improvement: Dict[str, Any]) -> None:
        """Log an improvement"""
        self.logs.append(improvement)
    
    def record(self, improvement: Dict[str, Any]) -> None:
        """Record an improvement (alias for log_improvement)"""
        self.logs.append(improvement)
    
    def save(self) -> None:
        """Save logs to file"""
        with open(self.log_path, 'w') as f:
            json.dump(self.logs, f, indent=2, default=str)
    
    def load(self) -> List[Dict[str, Any]]:
        """Load logs from file"""
        if self.log_path.exists():
            with open(self.log_path, 'r') as f:
                self.logs = json.load(f)
        return self.logs
    
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent improvements"""
        return self.logs[-limit:]

    def calculate_total_impact(self) -> Dict[str, int]:
        """Calculate total impact across all logged improvements."""
        impact: Dict[str, int] = {}
        for entry in self.logs:
            imp_type = entry.get("type", "unknown")
            impact[imp_type] = impact.get(imp_type, 0) + 1
        return impact
