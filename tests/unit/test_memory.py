# tests/unit/test_memory.py
"""
Unit tests for HELENA Memory
"""
import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from helena_core.memory import VectorStore, HELENAMemory

class TestVectorStore(unittest.TestCase):
    """Test vector store"""
    
    def setUp(self):
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()
        self.store = VectorStore(
            storage_path=self.temp_dir,
            dimension=384
        )
    
    def test_add_and_search(self):
        """Test adding and searching memories"""
        # Add test memory
        success = self.store.add(
            memory_id="test_mem_1",
            content="This is a test memory",
            embedding=[0.1] * 384,
            metadata={"type": "test"}
        )
        self.assertTrue(success)
        
        # Search
        results = self.store.search(
            query_embedding=[0.1] * 384,
            limit=5,
            threshold=0.5
        )
        
        self.assertIsInstance(results, list)
    
    def test_get_and_delete(self):
        """Test getting and deleting memories"""
        # Add memory
        self.store.add(
            memory_id="test_mem_2",
            content="Another test",
            embedding=[0.2] * 384
        )
        
        # Get memory
        mem = self.store.get("test_mem_2")
        self.assertIsNotNone(mem)
        self.assertEqual(mem['content'], "Another test")
        
        # Delete memory
        success = self.store.delete("test_mem_2")
        self.assertTrue(success)
        
        # Verify deletion
        mem = self.store.get("test_mem_2")
        self.assertIsNone(mem)
    
    def test_stats(self):
        """Test statistics"""
        # Add some memories
        for i in range(3):
            self.store.add(
                memory_id=f"stats_{i}",
                content=f"Stats test {i}",
                embedding=[0.3] * 384
            )
        
        stats = self.store.get_stats()
        self.assertEqual(stats['total_memories'], 3)
        self.assertIn('adds', stats)
    
    def tearDown(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
