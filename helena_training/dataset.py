"""
Training dataset management with persistent JSON storage.
"""
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict


class TrainingDataset:
    """Persistent training dataset with categorized storage and retrieval."""

    @staticmethod
    def _safe_category(category: str) -> str:
        """Sanitise a category name to prevent path traversal."""
        # BUGFIX #28: category names were used directly in file paths,
        # allowing path traversal (e.g. "../../../etc/exploit")
        import re
        # Keep only alphanumeric, underscore, hyphen, and dot
        safe = re.sub(r'[^\w.\-]', '_', category)
        # Remove leading dots to prevent hidden files / relative path tricks
        safe = safe.lstrip('.')
        # Fall back to 'general' if nothing remains
        return safe or 'general'

    def __init__(self, storage_path: str, max_size: int = 10_000):
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._data: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._load()

    def add(self, item: Dict[str, Any], category: str = "general") -> None:
        """Add an item to the dataset under *category*."""
        item.setdefault("timestamp", time.time())
        # BUGFIX #28: sanitize category to prevent path traversal on save
        category = self._safe_category(category)
        bucket = self._data[category]
        bucket.append(item)
        if len(bucket) > self.max_size:
            self._data[category] = bucket[-self.max_size:]

    def get_all(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all items, optionally filtered by category."""
        if category is not None:
            return list(self._data.get(category, []))
        items: List[Dict[str, Any]] = []
        for bucket in self._data.values():
            items.extend(bucket)
        return items

    def get_recent(self, category: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the *limit* most-recent items in *category*."""
        bucket = self._data.get(category, [])
        return bucket[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Return a summary of stored data."""
        stats: Dict[str, Any] = {"categories": {}, "total_items": 0}
        for cat, items in self._data.items():
            stats["categories"][cat] = len(items)
            stats["total_items"] += len(items)
        return stats

    def save(self) -> None:
        """Persist all data to disk as JSON files (one per category)."""
        for category, items in self._data.items():
            path = self.storage_path / f"{self._safe_category(category)}.json"
            with open(path, "w") as fh:
                json.dump(items, fh, indent=2, default=str)

    def _load(self) -> None:
        """Load previously-persisted data from disk."""
        if not self.storage_path.exists():
            return
        for path in self.storage_path.glob("*.json"):
            category = path.stem
            try:
                with open(path) as fh:
                    self._data[category] = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

    load = _load
