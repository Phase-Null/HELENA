# examples/kernel_usage.py
"""
Example usage of HELENA Kernel
"""
import time
from pathlib import Path

# Import kernel components
from helena_core.kernel import (
    HELENAKernel,
    TaskPriority,
    OperationalMode
)
from helena_core.utils.config_manager import get_config_manager
from helena_core.utils.logging import init_logging

def main():
    """Example kernel usage"""
    
    # Initialize logging
    logger = init_logging(
        log_directory=Path("./logs"),
        max_log_size_mb=10,
        log_retention_days=7
    )
    
    # Get configuration
    config_manager = get_config_manager(Path("./config.yaml"))
    config_manager.initialize("example_operator")
    
    # Create kernel
    kernel = HELENAKernel(
        operator_id="example_operator",
        config_manager=config_manager
    )
    
    # Initialize kernel
    if not kernel.initialize():
        print("Failed to initialize kernel")
        return
    
    print(f"Kernel initialized in {kernel.mode.name} mode")
    
    # Submit some tasks
    tasks = []
    
    # Task 1: Code generation (high priority)
    task_id = kernel.submit_task(
        command="code_generate",
        parameters={
            "language": "python",
            "description": "Calculate fibonacci sequence",
            "optimize_for": "clarity"
        },
        source="operator",
        priority=TaskPriority.HIGH,
        metadata={"request_type": "example"}
    )
    
    if task_id:
        tasks.append(task_id)
        print(f"Submitted code generation task: {task_id}")
    
    # Task 2: Memory query (normal priority)
    task_id = kernel.submit_task(
        command="memory_retrieve",
        parameters={
            "query": "python fibonacci examples",
            "limit": 5
        },
        source="operator",
        priority=TaskPriority.NORMAL
    )
    
    if task_id:
        tasks.append(task_id)
        print(f"Submitted memory query task: {task_id}")
    
    # Change mode to TOOL
    print("\nChanging to TOOL mode...")
    result = kernel.change_mode(OperationalMode.TOOL)
    print(f"Mode change result: {result}")
    
    # Submit task in TOOL mode
    task_id = kernel.submit_task(
        command="code_execute",
        parameters={
            "code": "print('Hello from TOOL mode')",
            "language": "python"
        },
        source="operator",
        priority=TaskPriority.NORMAL
    )
    
    if task_id:
        tasks.append(task_id)
        print(f"Submitted execution task in TOOL mode: {task_id}")
    
    # Get system status
    print("\nGetting system status...")
    status = kernel.get_system_status()
    print(f"Mode: {status['mode']}")
    print(f"Tasks processed: {status['metrics']['tasks_processed']}")
    print(f"Queue size: {status['queue']['queue_sizes']}")
    
    # Check task statuses
    print("\nChecking task statuses...")
    for task_id in tasks:
        status = kernel.get_task_status(task_id)
        if status:
            print(f"Task {task_id}: {status.get('status', 'unknown')}")
        else:
            print(f"Task {task_id}: not found")
    
    # Simulate some processing time
    print("\nWaiting for task processing...")
    time.sleep(2)
    
    # Get final status
    status = kernel.get_system_status()
    print(f"\nFinal status:")
    print(f"  Success rate: {status['metrics']['success_rate']:.2%}")
    print(f"  Avg processing time: {status['metrics']['avg_processing_time']:.3f}s")
    
    # Shutdown
    print("\nShutting down kernel...")
    kernel.shutdown(graceful=True)
    print("Kernel shutdown complete")

if __name__ == "__main__":
    main()
