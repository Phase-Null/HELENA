# helena_core/memory/vector_store.py
"""
Vector memory store for semantic similarity search
"""
import numpy as np
import json
import pickle
import zlib
import hashlib
import time
import threading
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
import logging
from pathlib import Path
import struct
from collections import defaultdict, deque

import chromadb
from chromadb.config import Settings
import chromadb.errors

logger = logging.getLogger(__name__)

class MemoryType(Enum):
    """Types of memories"""
    CODE = auto()
    DOCUMENTATION = auto()
    EXECUTION_RESULT = auto()
    ERROR = auto()
    SUCCESS_PATTERN = auto()
    OPERATOR_PREFERENCE = auto()
    SECURITY_PATTERN = auto()
    TRAINING_DATA = auto()

class MemoryPriority(Enum):
    """Memory priority levels"""
    CRITICAL = auto()
    HIGH = auto()
    NORMAL = auto()
    LOW = auto()
    ARCHIVAL = auto()

@dataclass
class MemoryEntry:
    """Single memory entry"""
    id: str
    content: str
    embedding: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    memory_type: MemoryType = MemoryType.DOCUMENTATION
    priority: MemoryPriority = MemoryPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = 0.0
    embedding_model: str = "all-MiniLM-L6-v2"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "metadata": self.metadata,
            "memory_type": self.memory_type.name,
            "priority": self.priority.name,
            "timestamp": self.timestamp,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "embedding_model": self.embedding_model
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        """Create from dictionary"""
        entry = cls(
            id=data["id"],
            content=data["content"],
            embedding=np.array(data["embedding"]) if data["embedding"] else None,
            metadata=data["metadata"],
            memory_type=MemoryType[data["memory_type"]],
            priority=MemoryPriority[data["priority"]],
            timestamp=data["timestamp"],
            access_count=data["access_count"],
            last_accessed=data["last_accessed"],
            embedding_model=data["embedding_model"]
        )
        return entry

class VectorStore:
    """
    Vector memory store using ChromaDB for efficient similarity search
    """
    
    def __init__(self, 
                 storage_path: str,
                 collection_name: str = "helena_memories",
                 dimension: int = 384):
        """
        Initialize vector store
        
        Args:
            storage_path: Path to persistent storage
            collection_name: Name of ChromaDB collection
            dimension: Vector dimension (must match embedding model)
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.dimension = dimension
        self.collection_name = collection_name
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(collection_name)
            logger.info(f"Loaded existing collection '{collection_name}'")
        except chromadb.errors.NotFoundError:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": f"HELENA memory system - {collection_name}"}
            )
            logger.info(f"Created new collection '{collection_name}'")
        
        self.lock = threading.RLock()
        self.stats = {
            "adds": 0,
            "queries": 0,
            "updates": 0,
            "deletes": 0
        }
        
        logger.info(f"VectorStore initialized at {storage_path}")
    
    def add(self, 
            memory_id: str,
            content: str,
            embedding: List[float],
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a memory to the vector store
        
        Args:
            memory_id: Unique identifier
            content: Text content
            embedding: Vector embedding
            metadata: Optional metadata
            
        Returns:
            bool: Success status
        """
        with self.lock:
            try:
                # Prepare metadata
                if metadata is None:
                    metadata = {}
                
                # Add timestamp if not present
                if "timestamp" not in metadata:
                    metadata["timestamp"] = time.time()
                
                # Add to collection
                self.collection.add(
                    ids=[memory_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[metadata]
                )
                
                self.stats["adds"] += 1
                logger.debug(f"Added memory {memory_id[:12]}...")
                return True
                
            except Exception as e:
                logger.error(f"Failed to add memory {memory_id}: {e}")
                return False
    
    def search(self, 
               query_embedding: List[float],
               limit: int = 10,
               threshold: float = 0.7,
               where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar memories
        
        Args:
            query_embedding: Query vector
            limit: Maximum results
            threshold: Minimum similarity threshold
            where: Optional metadata filter
            
        Returns:
            List of matching memories with similarity scores
        """
        with self.lock:
            try:
                self.stats["queries"] += 1
                
                # Execute query
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where=where
                )
                
                # Format results
                memories = []
                if results['ids'] and results['ids'][0]:
                    for i, (mem_id, doc, meta, dist) in enumerate(zip(
                        results['ids'][0],
                        results['documents'][0],
                        results['metadatas'][0],
                        results['distances'][0]
                    )):
                        # Convert distance to similarity (1 - distance)
                        similarity = 1.0 - dist
                        
                        if similarity >= threshold:
                            memories.append({
                                'id': mem_id,
                                'content': doc,
                                'metadata': meta,
                                'similarity': similarity,
                                'distance': dist
                            })
                
                logger.debug(f"Search returned {len(memories)} results")
                return memories
                
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
    
    def update(self, 
               memory_id: str,
               content: Optional[str] = None,
               embedding: Optional[List[float]] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update an existing memory
        
        Args:
            memory_id: Memory identifier
            content: New content (if any)
            embedding: New embedding (if any)
            metadata: New metadata (if any)
            
        Returns:
            bool: Success status
        """
        with self.lock:
            try:
                # Check if memory exists
                existing = self.get(memory_id)
                if not existing:
                    logger.warning(f"Memory {memory_id} not found for update")
                    return False
                
                # Update fields
                if content is not None:
                    self.collection.update(
                        ids=[memory_id],
                        documents=[content]
                    )
                
                if embedding is not None:
                    self.collection.update(
                        ids=[memory_id],
                        embeddings=[embedding]
                    )
                
                if metadata is not None:
                    # Merge with existing metadata
                    merged_meta = existing['metadata'].copy()
                    merged_meta.update(metadata)
                    self.collection.update(
                        ids=[memory_id],
                        metadatas=[merged_meta]
                    )
                
                self.stats["updates"] += 1
                logger.debug(f"Updated memory {memory_id[:12]}...")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update memory {memory_id}: {e}")
                return False
    
    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory
        
        Args:
            memory_id: Memory identifier
            
        Returns:
            bool: Success status
        """
        with self.lock:
            try:
                self.collection.delete(ids=[memory_id])
                self.stats["deletes"] += 1
                logger.debug(f"Deleted memory {memory_id[:12]}...")
                return True
                
            except Exception as e:
                logger.error(f"Failed to delete memory {memory_id}: {e}")
                return False
    
    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific memory by ID
        
        Args:
            memory_id: Memory identifier
            
        Returns:
            Memory data or None if not found
        """
        with self.lock:
            try:
                results = self.collection.get(ids=[memory_id])
                
                if results['ids']:
                    return {
                        'id': results['ids'][0],
                        'content': results['documents'][0] if results['documents'] else None,
                        'metadata': results['metadatas'][0] if results['metadatas'] else {}
                    }
                return None
                
            except Exception as e:
                logger.error(f"Failed to get memory {memory_id}: {e}")
                return None
    
    def get_all_ids(self) -> List[str]:
        """
        Get all memory IDs
        
        Returns:
            List of memory IDs
        """
        with self.lock:
            try:
                results = self.collection.get()
                return results['ids'] if results['ids'] else []
                
            except Exception as e:
                logger.error(f"Failed to get all IDs: {e}")
                return []
    
    def count(self) -> int:
        """
        Get total number of memories
        
        Returns:
            Memory count
        """
        with self.lock:
            try:
                return self.collection.count()
            except Exception as e:
                logger.error(f"Failed to get count: {e}")
                return 0
    
    def clear(self) -> bool:
        """
        Clear all memories
        
        Returns:
            bool: Success status
        """
        with self.lock:
            try:
                # Delete and recreate collection
                self.client.delete_collection(self.collection_name)
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": f"HELENA memory system - {self.collection_name}"}
                )
                
                # Reset stats
                self.stats = {k: 0 for k in self.stats}
                
                logger.info("Vector store cleared")
                return True
                
            except Exception as e:
                logger.error(f"Failed to clear vector store: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get store statistics
        
        Returns:
            Dictionary with statistics
        """
        with self.lock:
            stats = self.stats.copy()
            stats["total_memories"] = self.count()
            stats["collection"] = self.collection_name
            return stats

class EncryptedVectorStore(VectorStore):
    """
    Vector store with encryption for sensitive memories
    """
    
    def __init__(self, 
                 storage_path: str,
                 encryption_manager,
                 collection_name: str = "helena_memories_encrypted",
                 dimension: int = 384):
        """
        Initialize encrypted vector store
        
        Args:
            storage_path: Path to persistent storage
            encryption_manager: Encryption manager instance
            collection_name: Name of ChromaDB collection
            dimension: Vector dimension
        """
        super().__init__(storage_path, collection_name, dimension)
        self.encryption = encryption_manager
    
    def add_encrypted(self,
                     memory_id: str,
                     content: str,
                     embedding: List[float],
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add encrypted memory
        
        Args:
            memory_id: Unique identifier
            content: Text content (will be encrypted)
            embedding: Vector embedding
            metadata: Optional metadata (will be encrypted)
            
        Returns:
            bool: Success status
        """
        try:
            # Encrypt content
            encrypted_content = self.encryption.encrypt_string(
                content,
                purpose=f"memory:{memory_id}"
            )
            
            # Encrypt metadata if present
            encrypted_metadata = {}
            if metadata:
                meta_str = json.dumps(metadata)
                encrypted_meta = self.encryption.encrypt_string(
                    meta_str,
                    purpose=f"memory_meta:{memory_id}"
                )
                encrypted_metadata = {"encrypted_data": encrypted_meta}
            
            # Add to store
            return self.add(
                memory_id=f"enc_{memory_id}",
                content=encrypted_content,
                embedding=embedding,
                metadata={
                    **encrypted_metadata,
                    "encrypted": True,
                    "original_id": memory_id
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to add encrypted memory: {e}")
            return False
    
    def get_encrypted(self, encrypted_id: str) -> Optional[Dict[str, Any]]:
        """
        Get and decrypt encrypted memory
        
        Args:
            encrypted_id: Encrypted memory ID
            
        Returns:
            Decrypted memory data or None
        """
        try:
            result = self.get(encrypted_id)
            if not result:
                return None
            
            # Decrypt content
            decrypted_content = self.encryption.decrypt_string(
                result['content'],
                purpose=f"memory:{result['metadata']['original_id']}"
            )
            
            # Decrypt metadata if present
            decrypted_metadata = {}
            if "encrypted_data" in result['metadata']:
                meta_str = self.encryption.decrypt_string(
                    result['metadata']['encrypted_data'],
                    purpose=f"memory_meta:{result['metadata']['original_id']}"
                )
                decrypted_metadata = json.loads(meta_str)
            
            return {
                'id': result['id'],
                'content': decrypted_content,
                'metadata': decrypted_metadata,
                'original_id': result['metadata']['original_id']
            }
            
        except Exception as e:
            logger.error(f"Failed to get encrypted memory: {e}")
            return None
