# helena_core/memory/__init__.py
"""
HELENA Memory System – hybrid vector + graph memory.

The ``HELENAMemory`` facade combines:
* **VectorStore** (ChromaDB) – semantic similarity search via embeddings.
* **GraphMemory** (NetworkX) – relational / structural queries.

Embeddings are generated on-CPU with a lightweight bag-of-words hasher
so the system works fully offline with zero model downloads.
"""
import hashlib
import math
import re
import time
import logging
from typing import Dict, List, Any, Optional

from .vector_store import (
    VectorStore, MemoryType, MemoryPriority, MemoryEntry, EncryptedVectorStore,
)
from .graph_memory import GraphMemory
from ..utils.logging import get_logger

logger = get_logger()

__all__ = [
    "VectorStore",
    "MemoryType",
    "MemoryPriority",
    "MemoryEntry",
    "EncryptedVectorStore",
    "GraphMemory",
    "HELENAMemory",
]


# ── Lightweight offline embedder ──────────────────────────────────

class _OfflineEmbedder:
    """
    Deterministic bag-of-words hash embedder that requires **no** model
    files.  Each token is hashed to a fixed set of dimensions and the
    resulting vector is L2-normalised.  This gives a useful – if
    imperfect – similarity signal for free.

    Dimension default = 384 (same as all-MiniLM-L6-v2 so the
    VectorStore dimensionality stays consistent).
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self._token_re = re.compile(r"[a-zA-Z0-9_]+")

    def embed(self, text: str) -> List[float]:
        tokens = self._token_re.findall(text.lower())
        vec = [0.0] * self.dimension
        for token in tokens:
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            for i in range(4):                       # 4 active dims per token
                idx = (h >> (i * 16)) % self.dimension
                sign = 1.0 if ((h >> (64 + i)) & 1) == 0 else -1.0
                vec[idx] += sign
        # L2 normalise
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ── Main memory facade ────────────────────────────────────────────

class HELENAMemory:
    """
    Unified memory interface consumed by the kernel, training pipeline,
    and desktop GUI.
    """

    def __init__(self, config_manager) -> None:
        self.config = config_manager
        mem_cfg = config_manager.get_section("memory") or {}
        dim = mem_cfg.get("vector_dimension", 384) if isinstance(mem_cfg, dict) else 384

        storage_root = mem_cfg.get("storage_path", "./helena_memory") if isinstance(mem_cfg, dict) else "./helena_memory"

        # Embedder
        self._embedder = _OfflineEmbedder(dimension=dim)

        # Vector store (semantic similarity)
        self.vector_store = VectorStore(
            storage_path=storage_root,
            dimension=dim,
        )

        # Graph store (relational knowledge)
        self.graph = GraphMemory(storage_path=storage_root + "/graph")

        logger.info("Memory", "HELENA Memory system initialised (vector + graph)")

    # ── Store ─────────────────────────────────────────────────────

    def store(self, content: str, metadata: Optional[Dict[str, Any]] = None,
              memory_type: str = "general",
              relationships: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Store a memory in both vector and graph stores.

        Parameters
        ----------
        content : str
            The textual content to remember.
        metadata : dict, optional
            Arbitrary metadata attached to the entry.
        memory_type : str
            Category tag (e.g. "code", "error", "operator").
        relationships : list[dict], optional
            Each dict has keys ``target``, ``edge_type`` (optional).

        Returns
        -------
        str – the generated memory id.
        """
        if metadata is None:
            metadata = {}
        metadata["memory_type"] = memory_type
        metadata["timestamp"] = time.time()

        memory_id = hashlib.md5(
            (content + str(metadata.get("timestamp", ""))).encode()
        ).hexdigest()[:16]

        embedding = self._embedder.embed(content)

        self.vector_store.add(
            memory_id=memory_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
        )

        # Also add to graph
        self.graph.add_node(memory_id, node_type=memory_type,
                            metadata={"preview": content[:120]})

        if relationships:
            for rel in relationships:
                self.graph.add_edge(
                    memory_id,
                    rel["target"],
                    edge_type=rel.get("edge_type", "RELATED_TO"),
                )

        return memory_id

    # ── Search ────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 5,
               threshold: float = 0.3) -> List[Dict[str, Any]]:
        """Semantic search via vector embeddings."""
        embedding = self._embedder.embed(query)
        return self.vector_store.search(
            query_embedding=embedding,
            limit=limit,
            threshold=threshold,
        )

    def search_graph(self, query: str, node_type: Optional[str] = None,
                     limit: int = 20) -> List[Dict[str, Any]]:
        """Structural search via the knowledge graph."""
        return self.graph.search_nodes(query, node_type=node_type, limit=limit)

    def get_related(self, memory_id: str, depth: int = 2) -> Dict[str, Any]:
        """Return the neighbourhood around *memory_id* in the graph."""
        return self.graph.get_neighbours(memory_id, depth=depth)

    # ── Persistence ───────────────────────────────────────────────

    def save(self) -> None:
        """Persist graph to disk (vector store auto-persists via ChromaDB)."""
        self.graph.save()

    # ── Stats ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Combined statistics from both stores."""
        return {
            "vector": self.vector_store.get_stats(),
            "graph": self.graph.get_stats(),
        }
