---
tags: [architecture, memory]
date: 2026-03-05
status: active
component: helena_core/memory/
bugs: [17, 19]
---

# Memory System — HELENAMemory Hybrid Architecture

HELENAMemory is a facade combining ChromaDB vector store (semantic similarity) with NetworkX graph memory (relational knowledge). Both are accessed through the unified `HELENAMemory` interface.

> [!warning] Known Limitation
> Cross-session fact recall is unreliable. ChromaDB returns fuzzy matches; Mistral hallucinates to fill gaps. Phase 3 will fix with structured FactStore. Memory injection is restricted to non-GREETING, non-QUESTION intents to prevent old conversations polluting chat responses.

---

## Architecture

```
HELENAMemory (facade)
  ├── _OfflineEmbedder        — 384-dim BoW hash, no model download needed
  ├── VectorStore (ChromaDB)   — semantic similarity search
  │     └── collection: "helena_memories"
  │     └── PersistentClient at storage_path
  ├── EncryptedVectorStore     — extends VectorStore with EncryptionManager
  └── GraphMemory (NetworkX)   — relational / structural queries
        └── DiGraph with 5 node types, 8 edge types
        └── Persisted as JSON (node-link format)
```

---

## _OfflineEmbedder (`helena_core/memory/__init__.py`, lines 41–67)

Deterministic bag-of-words hash embedder. No model files required. Each token hashed to fixed dimensions, L2-normalized.

| Attribute | Value |
|-----------|-------|
| `dimension` | 384 (same as all-MiniLM-L6-v2) |
| `_token_re` | `[a-zA-Z0-9_]+` regex pattern |

Algorithm:
1. Tokenize text into alphanumeric tokens
2. For each token: `sha256(token) → int → 4 active dims per token`
3. Index: `(h >> (i * 16)) % dimension`, sign: `+1/-1` based on bit
4. L2 normalize final vector

> [!info] Design Trade-off
> Fuzzy but works offline. Not suitable for exact fact recall. Phase 3 will add structured FactStore for named facts (operator name, preferences, numbers).

---

## VectorStore (`helena_core/memory/vector_store.py`)

ChromaDB wrapper with thread-safe operations (`threading.RLock`).

### MemoryType (Enum)

| Type | Purpose |
|------|---------|
| CODE | Source code snippets |
| DOCUMENTATION | Architecture docs |
| EXECUTION_RESULT | Task outputs |
| ERROR | Error patterns |
| SUCCESS_PATTERN | Working approaches |
| OPERATOR_PREFERENCE | User preferences |
| SECURITY_PATTERN | Security events |
| TRAINING_DATA | Training inputs |

### MemoryPriority (Enum)

CRITICAL → HIGH → NORMAL → LOW → ARCHIVAL

### Key Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `add()` | `(memory_id, content, embedding, metadata)` → `bool` | Store with embedding |
| `search()` | `(query_embedding, limit, threshold, where)` → `List[Dict]` | Semantic similarity |
| `update()` | `(memory_id, content, embedding, metadata)` → `bool` | Modify existing |
| `delete()` | `(memory_id)` → `bool` | Remove entry |
| `get()` | `(memory_id)` → `Optional[Dict]` | Retrieve by ID |
| `get_all_ids()` | → `List[str]` | List all IDs |
| `count()` | → `int` | Total entries |
| `clear()` | → `bool` | Reset collection |

> [!warning] Bug #17 — Similarity Calculation Wrong for L2 Distance
> `similarity = 1.0 - dist` assumes cosine distance, but ChromaDB defaults to L2. Can produce negative values. Fixed to `similarity = 1.0 / (1.0 + dist)` (standard L2→similarity conversion). See [[Bug Fixes Registry#Bug 17]].

---

## GraphMemory (`helena_core/memory/graph_memory.py`)

NetworkX DiGraph for relational knowledge. JSON persistence via `node_link_data()`.

### Node Types

| Type | Purpose |
|------|---------|
| concept | Ideas, keywords (e.g. "encryption") |
| module | Python paths (e.g. "helena_core.kernel.core") |
| task | Historical task IDs |
| entity | Operators, files, external systems |
| pattern | Recurring patterns |

### Edge Types

`DEPENDS_ON`, `RELATED_TO`, `CAUSED_BY`, `PART_OF`, `LEARNED_FROM`, `USED_BY`, `SIMILAR_TO`, `TRIGGERS`

### Key Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `add_node()` | `(node_id, node_type, metadata)` | Create/update node |
| `add_edge()` | `(source, target, edge_type, weight, metadata)` | Link nodes (auto-creates missing) |
| `find_path()` | `(source, target)` → `Optional[List[str]]` | Shortest path |
| `get_neighbours()` | `(node_id, depth, edge_type)` → Dict | Local neighbourhood |
| `search_nodes()` | `(query, node_type, limit)` | Substring search |
| `get_most_connected()` | `(limit)` → `List[Tuple[str, int]]` | Highest-degree nodes |

---

## HELENAMemory Facade (`helena_core/memory/__init__.py`)

### Key Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `store()` | `(content, metadata, memory_type, relationships)` → `str` | Store in both vector + graph |
| `search()` | `(query, limit=5, threshold=0.3)` → `List[Dict]` | Semantic search via embeddings |
| `search_graph()` | `(query, node_type, limit)` | Structural search |
| `get_related()` | `(memory_id, depth=2)` → `Dict` | Graph neighbourhood |
| `save()` | — | Persist graph (ChromaDB auto-persists) |

> [!info] Search Threshold
> Threshold raised from **0.2 → 0.6** (in ARCHITECTURE.md) to reduce false matches. The facade uses `threshold=0.3` by default. VectorStore uses `threshold=0.7`.

---

## Bug #19 — Memory Vector Dimension Mismatch

MemoryConfig.vector_dimension defaults to 768, but _OfflineEmbedder produces 384-dim vectors. Changed to 384. See [[Bug Fixes Registry#Bug 19]].

---

## Related Notes

- [[Kernel]] — HELENAMemory initialized in kernel startup
- [[Chat Engine]] — `memory.search()` called in chat pipeline
- [[Bug Fixes Registry]] — Bug #17 (L2 similarity), Bug #19 (dimension mismatch)
