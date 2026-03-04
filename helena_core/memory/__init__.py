# helena_core/memory/__init__.py
"""
HELENA Memory System
"""
from .vector_store import VectorStore, MemoryType, MemoryPriority, MemoryEntry, EncryptedVectorStore
from ..utils.logging import get_logger

logger = get_logger()

__all__ = [
    'VectorStore',
    'MemoryType',
    'MemoryPriority',
    'MemoryEntry',
    'EncryptedVectorStore'
]

class HELENAMemory:
    """
    Main memory interface for HELENA
    """
    
    def __init__(self, config_manager):
        self.config = config_manager
        
        # Get memory config
        mem_config = config_manager.get_section("memory") or {}
        
        # Initialize vector store
        self.vector_store = VectorStore(
            storage_path="./helena_memory",
            dimension=mem_config.get('vector_dimension', 384)
        )
        
        logger.info("Memory", "HELENA Memory system initialized")
    
    def store(self, content: str, metadata: dict[str, any]) -> str:
        """Store a memory"""
        # Generate ID
        import hashlib
        memory_id = hashlib.md5(content.encode()).hexdigest()[:16]
        
        # For now, just store without embedding (would use embedding model)
        # Simplified for demonstration
        self.vector_store.add(
            memory_id=memory_id,
            content=content,
            embedding=[0.0] * 384,  # Placeholder
            metadata=metadata
        )
        
        return memory_id
    
    def search(self, query: str, limit: int = 5) -> list[dict[str, any]]:
        """Search memories"""
        # Simplified - would embed query
        return self.vector_store.search(
            query_embedding=[0.0] * 384,
            limit=limit
        )
    
    def get_stats(self) -> dict[str, any]:
        """Get memory statistics"""
        return self.vector_store.get_stats()
