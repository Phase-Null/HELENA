# helena_core/memory/graph_memory.py
"""
HELENA Graph Memory – relational knowledge store using NetworkX.

Stores concepts, entities, and relationships as a directed graph.
Complements the VectorStore (semantic similarity) with structural /
relational queries ("what connects A to B?", "what depends on X?").

Persistence is via JSON (node-link format) so no extra DB is needed.
"""
import json
import time
import threading
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict

import networkx as nx
from networkx.readwrite import json_graph

logger = logging.getLogger(__name__)


class GraphMemory:
    """
    Directed knowledge graph that HELENA uses to track relationships
    between concepts, code modules, operators, tasks, and errors.

    Node types
    ----------
    concept   – an idea or keyword (e.g. "encryption", "sorting")
    module    – a Python module path (e.g. "helena_core.kernel.core")
    task      – a historical task id
    entity    – an operator, file, or external system
    pattern   – a recognised recurring pattern

    Edge types
    ----------
    DEPENDS_ON, RELATED_TO, CAUSED_BY, PART_OF, LEARNED_FROM,
    USED_BY, SIMILAR_TO, TRIGGERS
    """

    EDGE_TYPES = frozenset({
        "DEPENDS_ON", "RELATED_TO", "CAUSED_BY", "PART_OF",
        "LEARNED_FROM", "USED_BY", "SIMILAR_TO", "TRIGGERS",
    })

    def __init__(self, storage_path: str) -> None:
        self._lock = threading.RLock()
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._graph_file = self.storage_path / "graph.json"

        self.graph: nx.DiGraph = nx.DiGraph()
        self._load()

        self._stats = {"adds": 0, "queries": 0, "edge_adds": 0}
        logger.info("GraphMemory initialised (%d nodes, %d edges)",
                     self.graph.number_of_nodes(), self.graph.number_of_edges())

    # ── Node operations ───────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str = "concept",
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add or update a node."""
        with self._lock:
            attrs: Dict[str, Any] = {
                "type": node_type,
                "created": time.time(),
                "access_count": 0,
            }
            if metadata:
                attrs.update(metadata)
            if self.graph.has_node(node_id):
                self.graph.nodes[node_id].update(attrs)
            else:
                self.graph.add_node(node_id, **attrs)
            self._stats["adds"] += 1

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return node attributes or *None*."""
        with self._lock:
            if not self.graph.has_node(node_id):
                return None
            data = dict(self.graph.nodes[node_id])
            data["id"] = node_id
            data["access_count"] = data.get("access_count", 0) + 1
            self.graph.nodes[node_id]["access_count"] = data["access_count"]
            self._stats["queries"] += 1
            return data

    def remove_node(self, node_id: str) -> bool:
        with self._lock:
            if self.graph.has_node(node_id):
                self.graph.remove_node(node_id)
                return True
            return False

    # ── Edge operations ───────────────────────────────────────────

    def add_edge(self, source: str, target: str,
                 edge_type: str = "RELATED_TO",
                 weight: float = 1.0,
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a directed edge (auto-creates missing nodes)."""
        with self._lock:
            for nid in (source, target):
                if not self.graph.has_node(nid):
                    self.add_node(nid)
            attrs: Dict[str, Any] = {
                "type": edge_type,
                "weight": weight,
                "created": time.time(),
            }
            if metadata:
                attrs.update(metadata)
            self.graph.add_edge(source, target, **attrs)
            self._stats["edge_adds"] += 1

    def get_edges(self, node_id: str, direction: str = "both"
                  ) -> List[Dict[str, Any]]:
        """Return edges for *node_id*. direction: 'in', 'out', or 'both'."""
        with self._lock:
            edges: List[Dict[str, Any]] = []
            if direction in ("out", "both"):
                for _, tgt, data in self.graph.out_edges(node_id, data=True):
                    edges.append({"source": node_id, "target": tgt, **data})
            if direction in ("in", "both"):
                for src, _, data in self.graph.in_edges(node_id, data=True):
                    edges.append({"source": src, "target": node_id, **data})
            self._stats["queries"] += 1
            return edges

    # ── Query helpers ─────────────────────────────────────────────

    def find_path(self, source: str, target: str) -> Optional[List[str]]:
        """Shortest path between two nodes (or *None*)."""
        with self._lock:
            try:
                return nx.shortest_path(self.graph, source, target)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None

    def get_neighbours(self, node_id: str, depth: int = 1,
                       edge_type: Optional[str] = None) -> Dict[str, Any]:
        """Return the local neighbourhood up to *depth* hops."""
        with self._lock:
            if not self.graph.has_node(node_id):
                return {"center": node_id, "nodes": [], "edges": []}
            sub = nx.ego_graph(self.graph, node_id, radius=depth)
            nodes = []
            for nid, data in sub.nodes(data=True):
                nodes.append({"id": nid, **data})
            edges = []
            for src, tgt, data in sub.edges(data=True):
                if edge_type and data.get("type") != edge_type:
                    continue
                edges.append({"source": src, "target": tgt, **data})
            self._stats["queries"] += 1
            return {"center": node_id, "nodes": nodes, "edges": edges}

    def search_nodes(self, query: str, node_type: Optional[str] = None,
                     limit: int = 20) -> List[Dict[str, Any]]:
        """Simple substring search across node IDs and metadata."""
        with self._lock:
            results: List[Dict[str, Any]] = []
            q = query.lower()
            for nid, data in self.graph.nodes(data=True):
                if node_type and data.get("type") != node_type:
                    continue
                # Match on id or any string metadata value
                searchable = nid.lower()
                for v in data.values():
                    if isinstance(v, str):
                        searchable += " " + v.lower()
                if q in searchable:
                    results.append({"id": nid, **data})
                    if len(results) >= limit:
                        break
            self._stats["queries"] += 1
            return results

    def get_most_connected(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Return nodes with the highest degree."""
        with self._lock:
            degree_list = sorted(self.graph.degree(), key=lambda x: x[1], reverse=True)
            return degree_list[:limit]

    # ── Persistence ───────────────────────────────────────────────

    def save(self) -> None:
        """Persist graph to JSON."""
        with self._lock:
            data = json_graph.node_link_data(self.graph)
            with open(self._graph_file, "w") as fh:
                json.dump(data, fh, indent=2, default=str)
        logger.debug("GraphMemory saved (%d nodes)", self.graph.number_of_nodes())

    def _load(self) -> None:
        if self._graph_file.exists():
            try:
                with open(self._graph_file) as fh:
                    data = json.load(fh)
                self.graph = json_graph.node_link_graph(data, directed=True)
                logger.info("GraphMemory loaded from %s", self._graph_file)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("GraphMemory load failed (%s), starting fresh", exc)

    # ── Stats ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                **self._stats,
            }
