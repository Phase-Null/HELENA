# examples/memory_usage.py
"""
Example usage of HELENA Memory
"""
import time
from pathlib import Path

# Import memory components
from helena_core.memory import VectorStore

def main():
    """Example memory usage"""
    
    print("HELENA Memory Example")
    print("=" * 40)
    
    # Initialize vector store
    store = VectorStore(
        storage_path="./memory_test",
        dimension=384
    )
    
    print(f"\nVector store initialized with {store.count()} memories")
    
    # Add some memories
    print("\nAdding memories...")
    
    memories = [
        ("Python function to calculate factorial", {"type": "code", "language": "python"}),
        ("Error handling best practices", {"type": "documentation", "topic": "errors"}),
        ("Quick sort algorithm implementation", {"type": "code", "algorithm": "sorting"}),
        ("Memory management in Python", {"type": "documentation", "topic": "performance"}),
    ]
    
    for i, (content, meta) in enumerate(memories):
        mem_id = f"example_mem_{i}"
        # Simplified - in real usage would generate embedding
        embedding = [0.1 * i] * 384
        
        success = store.add(mem_id, content, embedding, meta)
        if success:
            print(f"  Added: {mem_id} - {content[:30]}...")
    
    print(f"\nTotal memories: {store.count()}")
    
    # Search
    print("\nSearching for 'python'...")
    # Simplified query embedding
    query_embedding = [0.1] * 384
    results = store.search(query_embedding, limit=3)
    
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['content'][:50]}... (similarity: {result['similarity']:.2f})")
    
    # Get a specific memory
    print("\nGetting memory 'example_mem_0'...")
    mem = store.get("example_mem_0")
    if mem:
        print(f"  Found: {mem['content']}")
        print(f"  Metadata: {mem['metadata']}")
    
    # Get statistics
    print("\nStatistics:")
    stats = store.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\nExample complete!")

if __name__ == "__main__":
    main()
