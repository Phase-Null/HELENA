# helena_core/kernel/core.py
"""
HELENA Kernel - The central reasoning and authority layer
"""
import asyncio
import time
import uuid
import threading
import queue
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
import logging
from concurrent.futures import ThreadPoolExecutor, Future
import hashlib
import json

from ..utils.logging import get_logger, LogType, LogLevel
from ..security.encryption import EncryptionManager
from .modes import OperationalMode, ModeProcessor
from .validation import ValidationChain, ValidationResult
from .personality import PersonalityEngine, ResponseFormatter

logger = get_logger()

class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0    # Security, kill switch, emergency
    HIGH = 1        # Operator commands, real-time responses
    NORMAL = 2      # Module requests, background processing
    LOW = 3         # Training, maintenance, cleanup
    BACKGROUND = 4  # Idle-time processing

class TaskStatus(Enum):
    """Task status states"""
    PENDING = auto()
    VALIDATING = auto()
    PROCESSING = auto()
    VALIDATED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

@dataclass
class TaskContext:
    """Context for task execution"""
    operator_id: str
    session_id: str
    source: str  # 'operator', 'module', 'system', 'training'
    permissions: Set[str]
    resource_budget: Dict[str, Any]  # CPU, RAM, time limits
    environmental_state: Dict[str, Any]  # System load, thermal, etc.

@dataclass
class TaskRequest:
    """Complete task request structure"""
    task_id: str
    command: str
    parameters: Dict[str, Any]
    context: TaskContext
    priority: TaskPriority
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "task_id": self.task_id,
            "command": self.command,
            "parameters": self.parameters,
            "context": asdict(self.context),
            "priority": self.priority.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskRequest':
        """Create from dictionary"""
        return cls(
            task_id=data["task_id"],
            command=data["command"],
            parameters=data["parameters"],
            context=TaskContext(**data["context"]),
            priority=TaskPriority(data["priority"]),
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {})
        )

@dataclass
class TaskResult:
    """Result of task execution"""
    task_id: str
    status: TaskStatus
    output: Any
    error: Optional[str] = None
    validation_result: Optional[ValidationResult] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    learning_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "validation_result": asdict(self.validation_result) if self.validation_result else None,
            "performance_metrics": self.performance_metrics,
            "learning_opportunities": self.learning_opportunities
        }

class TaskQueue:
    """Priority-based task queue with rate limiting"""
    
    def __init__(self, max_size: int = 1000):
        self.queues = {
            priority: queue.PriorityQueue(maxsize=max_size // 4)
            for priority in TaskPriority
        }
        self.lock = threading.RLock()
        self.task_map: Dict[str, TaskRequest] = {}
        self.stats = {
            "enqueued": 0,
            "dequeued": 0,
            "dropped": 0,
            "queue_sizes": {p.name: 0 for p in TaskPriority}
        }
    
    def enqueue(self, task: TaskRequest) -> bool:
        """Add task to appropriate priority queue"""
        with self.lock:
            if task.task_id in self.task_map:
                return False  # Task already exists
            
            priority_queue = self.queues[task.priority]
            
            try:
                # Use timestamp as secondary sort key for FIFO within priority
                priority_queue.put((task.priority.value, task.timestamp, task), block=False)
                self.task_map[task.task_id] = task
                self.stats["enqueued"] += 1
                self.stats["queue_sizes"][task.priority.name] = priority_queue.qsize()
                return True
            except queue.Full:
                # Try to drop low priority tasks
                if self._drop_low_priority():
                    return self.enqueue(task)  # Retry
                self.stats["dropped"] += 1
                return False
    
    def dequeue(self) -> Optional[TaskRequest]:
        """Get next highest priority task"""
        with self.lock:
            for priority in TaskPriority:
                queue_obj = self.queues[priority]
                if not queue_obj.empty():
                    try:
                        _, _, task = queue_obj.get(block=False)
                        del self.task_map[task.task_id]
                        self.stats["dequeued"] += 1
                        self.stats["queue_sizes"][priority.name] = queue_obj.qsize()
                        return task
                    except queue.Empty:
                        continue
            return None
    
    def _drop_low_priority(self) -> bool:
        """Drop lowest priority task to make room"""
        for priority in reversed(list(TaskPriority)):
            queue_obj = self.queues[priority]
            if not queue_obj.empty():
                try:
                    _, _, task = queue_obj.get(block=False)
                    del self.task_map[task.task_id]
                    self.stats["dropped"] += 1
                    self.stats["queue_sizes"][priority.name] = queue_obj.qsize()
                    return True
                except queue.Empty:
                    continue
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self.lock:
            return self.stats.copy()
    
    def clear(self):
        """Clear all queues"""
        with self.lock:
            for queue_obj in self.queues.values():
                while not queue_obj.empty():
                    try:
                        queue_obj.get(block=False)
                    except queue.Empty:
                        break
            self.task_map.clear()
            self.stats = {
                "enqueued": 0,
                "dequeued": 0,
                "dropped": 0,
                "queue_sizes": {p.name: 0 for p in TaskPriority}
            }

class PermissionManager:
    """Manage permissions based on operational mode and source"""
    
    def __init__(self):
        # Define permission matrix: mode -> command -> allowed
        self.permission_matrix = {
            OperationalMode.ENGINEERING: {
                "code_generate": True,
                "code_execute": True,
                "system_control": True,
                "memory_write": True,
                "module_load": True,
                "network_access": True,
                "training_start": True,
                "security_override": True,
            },
            OperationalMode.TOOL: {
                "code_generate": True,
                "code_execute": True,
                "system_control": False,
                "memory_write": False,
                "module_load": False,
                "network_access": False,
                "training_start": False,
                "security_override": False,
            },
            OperationalMode.DEFENSIVE: {
                "code_generate": False,
                "code_execute": False,
                "system_control": True,
                "memory_write": True,
                "module_load": False,
                "network_access": True,
                "training_start": False,
                "security_override": True,
            },
            OperationalMode.BACKGROUND: {
                "code_generate": False,
                "code_execute": False,
                "system_control": False,
                "memory_write": False,
                "module_load": False,
                "network_access": False,
                "training_start": False,
                "security_override": False,
            }
        }
        
        # Additional constraints based on source
        self.source_constraints = {
            "operator": set(self.permission_matrix[OperationalMode.ENGINEERING].keys()),  # Full access
            "module": {"code_generate", "code_execute", "memory_read"},  # Limited
            "system": set(self.permission_matrix[OperationalMode.ENGINEERING].keys()),  # Full
            "training": {"memory_read", "memory_write", "training_start"},  # Training only
        }
    
    def check_permission(self, 
                        mode: OperationalMode, 
                        command: str, 
                        source: str) -> bool:
        """Check if command is allowed in current mode and source"""
        try:
            # Get mode permissions
            mode_permissions = self.permission_matrix.get(mode, {})
            if not mode_permissions.get(command, False):
                return False
            
            # Check source constraints
            if source not in self.source_constraints:
                return False
            
            source_allowed = self.source_constraints[source]
            if command not in source_allowed:
                return False
            
            return True
            
        except Exception as e:
            logger.error("PermissionManager", f"Permission check failed: {e}")
            return False
    
    def get_available_commands(self, 
                              mode: OperationalMode, 
                              source: str) -> Set[str]:
        """Get all commands available for mode and source"""
        try:
            mode_permissions = self.permission_matrix.get(mode, {})
            source_allowed = self.source_constraints.get(source, set())
            
            available = set()
            for command, allowed in mode_permissions.items():
                if allowed and command in source_allowed:
                    available.add(command)
            
            return available
            
        except Exception:
            return set()

class LearningHook:
    """Hook for capturing learning opportunities from task execution"""
    
    def __init__(self):
        self.hooks: List[Callable[[TaskRequest, TaskResult], None]] = []
        self.learning_buffer = []
        self.buffer_size = 100
    
    def register(self, hook: Callable[[TaskRequest, TaskResult], None]):
        """Register a learning hook"""
        self.hooks.append(hook)
    
    def capture(self, request: TaskRequest, result: TaskResult):
        """Capture learning opportunity from task execution"""
        try:
            # Extract learning data
            learning_data = {
                "task_id": request.task_id,
                "command": request.command,
                "parameters": request.parameters,
                "context": request.context.to_dict() if hasattr(request.context, 'to_dict') else asdict(request.context),
                "result": result.to_dict(),
                "timestamp": time.time(),
                "success": result.status == TaskStatus.COMPLETED
            }
            
            # Add to buffer
            self.learning_buffer.append(learning_data)
            if len(self.learning_buffer) > self.buffer_size:
                self.learning_buffer.pop(0)
            
            # Execute hooks
            for hook in self.hooks:
                try:
                    hook(request, result)
                except Exception as e:
                    logger.error("LearningHook", f"Hook execution failed: {e}")
            
            # Log learning capture
            logger.debug("LearningHook", 
                        f"Captured learning opportunity from task {request.task_id}")
                        
        except Exception as e:
            logger.error("LearningHook", f"Failed to capture learning: {e}")
    
    def get_learning_data(self, 
                         limit: int = 50,
                         filter_success: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get learning data from buffer"""
        data = self.learning_buffer.copy()
        
        if filter_success is not None:
            data = [d for d in data if d["success"] == filter_success]
        
        return data[-limit:] if limit else data

class HELENAKernel:
    """
    Core reasoning engine and authority layer for HELENA
    """
    
    def __init__(self, 
                 operator_id: str,
                 config_manager,
                 memory_system = None,
                 runtime_manager = None):
        
        self.operator_id = operator_id
        self.config = config_manager
        self.memory = memory_system
        self.runtime = runtime_manager
        
        # Core state
        self.mode = OperationalMode.ENGINEERING
        self.active = False
        self.initialized = False
        
        # Components
        self.task_queue = TaskQueue()
        self.permission_manager = PermissionManager()
        self.validation_chain = ValidationChain()
        self.personality_engine = PersonalityEngine()
        self.response_formatter = ResponseFormatter()
        self.learning_hook = LearningHook()
        self.mode_processor = ModeProcessor(kernel=self)
        
        # Initialize LLM for chat
        try:
            from ..ml.llm import HybridLLM
            self.llm = HybridLLM()
        except Exception as e:
            logger.warning("HELENAKernel", f"Failed to initialize LLM: {e}")
            self.llm = None
        
        # Worker pool
        self.worker_pool = ThreadPoolExecutor(
            max_workers=4,  # Configurable
            thread_name_prefix="HELENA_Kernel_Worker"
        )
        
        # Task tracking
        self.active_tasks: Dict[str, Future] = {}
        self.task_history: List[Dict[str, Any]] = []
        self.max_history = 1000
        
        # Performance tracking
        self.metrics = {
            "tasks_processed": 0,
            "avg_processing_time": 0.0,
            "success_rate": 1.0,
            "validation_pass_rate": 1.0,
            "mode_changes": 0,
            "permission_denials": 0,
        }
        
        # Security state
        self.security_level = "NORMAL"
        self.lockdown_mode = False
        
        # Event loop
        self.event_loop = asyncio.new_event_loop()
        self.event_thread: Optional[threading.Thread] = None
        
        logger.info("HELENAKernel", f"Kernel initialized for operator: {operator_id}")
    
    def initialize(self) -> bool:
        """Initialize kernel components"""
        try:
            # Configure from settings
            personality_config = self.config.get_section("personality")
            self.personality_engine.configure(personality_config)
            self.response_formatter.configure(personality_config)
            
            # Setup validation chain
            self.validation_chain.setup_default_validators()
            
            # Register learning hooks
            self.learning_hook.register(self._learning_hook_memory)
            self.learning_hook.register(self._learning_hook_performance)
            
            # Load mode processors
            self.mode_processor.load_processors()
            
            # Start event loop
            self._start_event_loop()
            
            self.initialized = True
            logger.info("HELENAKernel", "Kernel components initialized")
            return True
            
        except Exception as e:
            logger.error("HELENAKernel", f"Initialization failed: {e}")
            return False
    
    def _start_event_loop(self):
        """Start async event loop in separate thread"""
        def run_loop():
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
        
        self.event_thread = threading.Thread(
            target=run_loop,
            daemon=True,
            name="HELENA_Kernel_EventLoop"
        )
        self.event_thread.start()
    
    def submit_task(self, 
                   command: str,
                   parameters: Dict[str, Any],
                   source: str = "operator",
                   priority: TaskPriority = TaskPriority.NORMAL,
                   metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Submit a task for processing
        Returns task_id if successful, None otherwise
        """
        if not self.initialized:
            logger.error("HELENAKernel", "Kernel not initialized")
            return None
        
        if self.lockdown_mode and priority != TaskPriority.CRITICAL:
            logger.warning("HELENAKernel", "Task rejected - lockdown mode active")
            return None
        
        # Create task
        task_id = f"task_{uuid.uuid4().hex[:16]}_{int(time.time())}"
        
        # Create context
        context = TaskContext(
            operator_id=self.operator_id,
            session_id=self._get_session_id(),
            source=source,
            permissions=self.permission_manager.get_available_commands(self.mode, source),
            resource_budget=self._calculate_resource_budget(priority),
            environmental_state=self._get_environmental_state()
        )
        
        # Create request
        request = TaskRequest(
            task_id=task_id,
            command=command,
            parameters=parameters,
            context=context,
            priority=priority,
            metadata=metadata or {}
        )
        
        # Check permissions
        if not self.permission_manager.check_permission(self.mode, command, source):
            logger.warning("HELENAKernel", 
                          f"Permission denied for {command} in mode {self.mode.name} from {source}")
            self.metrics["permission_denials"] += 1
            return None
        
        # Enqueue task
        if self.task_queue.enqueue(request):
            # Start processing if not already active
            if not self.active:
                self._start_processing()
            
            logger.debug("HELENAKernel", f"Task submitted: {task_id}")
            return task_id
        else:
            logger.error("HELENAKernel", f"Failed to enqueue task: {task_id}")
            return None
    
    def _start_processing(self):
        """Start task processing loop"""
        if self.active:
            return
        
        self.active = True
        
        # Submit processing job to worker pool
        future = self.worker_pool.submit(self._processing_loop)
        future.add_done_callback(self._processing_loop_done)
        
        logger.info("HELENAKernel", "Task processing started")
    
    def _processing_loop(self):
        """Main task processing loop"""
        try:
            while self.active:
                # Get next task
                task = self.task_queue.dequeue()
                if not task:
                    time.sleep(0.01)  # Small sleep to prevent CPU spin
                    continue
                
                # Process task
                result = self._process_single_task(task)
                
                # Store result
                self._store_task_result(task, result)
                
                # Update metrics
                self._update_metrics(task, result)
                
                # Trigger learning hooks
                self.learning_hook.capture(task, result)
                
                # Check for shutdown
                if not self.active:
                    break
                    
        except Exception as e:
            logger.error("HELENAKernel", f"Processing loop error: {e}")
            self.active = False
    
    def _processing_loop_done(self, future: Future):
        """Handle processing loop completion"""
        try:
            future.result()  # Re-raise any exceptions
        except Exception as e:
            logger.error("HELENAKernel", f"Processing loop failed: {e}")
        
        self.active = False
        logger.info("HELENAKernel", "Task processing stopped")
    
    def _process_single_task(self, task: TaskRequest) -> TaskResult:
        """Process a single task through the complete pipeline"""
        start_time = time.time()
        
        try:
            # Step 1: Validation
            validation_result = self.validation_chain.validate(task)
            if not validation_result.passed:
                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    output=None,
                    error=f"Validation failed: {validation_result.errors}",
                    validation_result=validation_result
                )
            
            # Step 2: Mode-specific processing
            mode_output = self.mode_processor.process(self.mode, task)
            
            # Step 3: Apply personality (if applicable)
            if self._should_apply_personality(task):
                personality_output = self.personality_engine.apply(
                    mode_output,
                    task.context
                )
            else:
                personality_output = mode_output
            
            # Step 4: Format response
            formatted_output = self.response_formatter.format(
                personality_output,
                task.context,
                self.mode
            )
            
            # Step 5: Create result
            processing_time = time.time() - start_time
            
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                output=formatted_output,
                validation_result=validation_result,
                performance_metrics={
                    "processing_time": processing_time,
                    "validation_time": validation_result.validation_time,
                    "mode_processing_time": mode_output.get("processing_time", 0),
                    "memory_used": 0  # Would be measured in production
                }
            )
            
            # Step 6: Extract learning opportunities
            result.learning_opportunities = self._extract_learning_opportunities(
                task, result
            )
            
            logger.debug("HELENAKernel", 
                        f"Task {task.task_id} completed in {processing_time:.3f}s")
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error("HELENAKernel", 
                        f"Task {task.task_id} failed: {e}")
            
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=str(e),
                performance_metrics={"processing_time": processing_time}
            )
    
    def _should_apply_personality(self, task: TaskRequest) -> bool:
        """Determine if personality should be applied to this task"""
        # Don't apply personality to system tasks or in tool mode
        if task.context.source == "system":
            return False
        
        if self.mode == OperationalMode.TOOL:
            return False
        
        # Check if task explicitly requests no personality
        if task.metadata.get("no_personality", False):
            return False
        
        return True
    
    def _extract_learning_opportunities(self, 
                                       task: TaskRequest, 
                                       result: TaskResult) -> List[Dict[str, Any]]:
        """Extract learning opportunities from task execution"""
        opportunities = []
        
        # Opportunity 1: Performance optimization
        if result.performance_metrics:
            if result.performance_metrics.get("processing_time", 0) > 1.0:  # Slow task
                opportunities.append({
                    "type": "performance_optimization",
                    "task_id": task.task_id,
                    "command": task.command,
                    "processing_time": result.performance_metrics["processing_time"],
                    "suggestion": "Consider optimizing processing pipeline"
                })
        
        # Opportunity 2: Validation patterns
        if result.validation_result:
            for issue in result.validation_result.issues:
                if issue["severity"] == "warning":
                    opportunities.append({
                        "type": "validation_refinement",
                        "issue": issue,
                        "suggestion": "Refine validation rules"
                    })
        
        # Opportunity 3: Error patterns (if any, though task succeeded)
        # This would capture near-misses
        
        return opportunities
    
    def _store_task_result(self, task: TaskRequest, result: TaskResult):
        """Store task result in history"""
        history_entry = {
            "task": task.to_dict(),
            "result": result.to_dict(),
            "timestamp": time.time()
        }
        
        self.task_history.append(history_entry)
        if len(self.task_history) > self.max_history:
            self.task_history.pop(0)
    
    def _update_metrics(self, task: TaskRequest, result: TaskResult):
        """Update performance metrics"""
        self.metrics["tasks_processed"] += 1
        
        # Update success rate
        if result.status == TaskStatus.COMPLETED:
            self.metrics["success_rate"] = (
                (self.metrics["success_rate"] * (self.metrics["tasks_processed"] - 1) + 1) 
                / self.metrics["tasks_processed"]
            )
        else:
            self.metrics["success_rate"] = (
                (self.metrics["success_rate"] * (self.metrics["tasks_processed"] - 1)) 
                / self.metrics["tasks_processed"]
            )
        
        # Update validation pass rate
        if result.validation_result and result.validation_result.passed:
            self.metrics["validation_pass_rate"] = (
                (self.metrics["validation_pass_rate"] * (self.metrics["tasks_processed"] - 1) + 1) 
                / self.metrics["tasks_processed"]
            )
        else:
            self.metrics["validation_pass_rate"] = (
                (self.metrics["validation_pass_rate"] * (self.metrics["tasks_processed"] - 1)) 
                / self.metrics["tasks_processed"]
            )
        
        # Update average processing time
        processing_time = result.performance_metrics.get("processing_time", 0)
        self.metrics["avg_processing_time"] = (
            (self.metrics["avg_processing_time"] * (self.metrics["tasks_processed"] - 1) + processing_time) 
            / self.metrics["tasks_processed"]
        )
    
    def change_mode(self, new_mode: OperationalMode) -> Dict[str, Any]:
        """Change operational mode"""
        old_mode = self.mode
        
        try:
            # Validate mode change
            if self.lockdown_mode and new_mode != OperationalMode.DEFENSIVE:
                return {
                    "success": False,
                    "error": "Cannot change mode during lockdown",
                    "old_mode": old_mode.name,
                    "new_mode": new_mode.name
                }
            
            # Update mode
            self.mode = new_mode
            self.metrics["mode_changes"] += 1
            
            # Adjust worker pool based on mode
            self._adjust_worker_pool(new_mode)
            
            # Log mode change
            logger.info("HELENAKernel", 
                       f"Mode changed: {old_mode.name} -> {new_mode.name}")
            
            return {
                "success": True,
                "old_mode": old_mode.name,
                "new_mode": new_mode.name,
                "available_commands": list(
                    self.permission_manager.get_available_commands(new_mode, "operator")
                )
            }
            
        except Exception as e:
            logger.error("HELENAKernel", f"Mode change failed: {e}")
            self.mode = old_mode  # Revert on error
            
            return {
                "success": False,
                "error": str(e),
                "old_mode": old_mode.name,
                "new_mode": new_mode.name
            }
    
    def _adjust_worker_pool(self, mode: OperationalMode):
        """Adjust worker pool size based on operational mode"""
        worker_config = {
            OperationalMode.ENGINEERING: 4,
            OperationalMode.TOOL: 2,
            OperationalMode.DEFENSIVE: 8,  # More workers for security
            OperationalMode.BACKGROUND: 1,
        }
        
        target_workers = worker_config.get(mode, 2)
        
        # In production, we would adjust the worker pool
        # For now, just log the intention
        logger.debug("HELENAKernel", 
                    f"Adjusting worker pool for {mode.name}: target={target_workers}")
    
    def set_lockdown_mode(self, enable: bool) -> bool:
        """Enable or disable lockdown mode"""
        if enable:
            if self.lockdown_mode:
                return False  # Already in lockdown
            
            self.lockdown_mode = True
            self.security_level = "LOCKDOWN"
            
            # Switch to defensive mode
            self.change_mode(OperationalMode.DEFENSIVE)
            
            # Clear non-critical tasks
            self._clear_non_critical_tasks()
            
            logger.critical("HELENAKernel", "Lockdown mode activated")
            return True
            
        else:
            if not self.lockdown_mode:
                return False  # Not in lockdown
            
            self.lockdown_mode = False
            self.security_level = "NORMAL"
            
            logger.info("HELENAKernel", "Lockdown mode deactivated")
            return True
    
    def _clear_non_critical_tasks(self):
        """Clear all non-critical tasks from queue during lockdown"""
        # In production, would iterate through queue and remove non-critical tasks
        # For now, clear entire queue (simplified)
        if self.lockdown_mode:
            self.task_queue.clear()
            logger.warning("HELENAKernel", "Cleared task queue for lockdown")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        # Check active tasks
        if task_id in self.active_tasks:
            future = self.active_tasks[task_id]
            if future.running():
                return {"status": "processing", "task_id": task_id}
            elif future.done():
                try:
                    result = future.result()
                    return {"status": "completed", "result": result.to_dict()}
                except Exception as e:
                    return {"status": "failed", "error": str(e)}
        
        # Check history
        for entry in reversed(self.task_history):
            if entry["task"]["task_id"] == task_id:
                return {
                    "status": "completed",
                    "result": entry["result"],
                    "timestamp": entry["timestamp"]
                }
        
        return None
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get complete system status"""
        queue_stats = self.task_queue.get_stats()
        
        return {
            "operator": self.operator_id,
            "mode": self.mode.name,
            "security_level": self.security_level,
            "lockdown": self.lockdown_mode,
            "active": self.active,
            "initialized": self.initialized,
            "metrics": self.metrics.copy(),
            "queue": queue_stats,
            "worker_pool": {
                "active_workers": self.worker_pool._max_workers,
                "pending_tasks": len(self.active_tasks)
            },
            "memory": {
                "task_history": len(self.task_history),
                "learning_buffer": len(self.learning_hook.learning_buffer)
            }
        }
    
    def shutdown(self, graceful: bool = True) -> bool:
        """Shutdown kernel"""
        try:
            logger.info("HELENAKernel", "Shutdown initiated")
            
            # Stop processing new tasks
            self.active = False
            
            if graceful:
                # Wait for current tasks to complete
                logger.info("HELENAKernel", "Waiting for active tasks...")
                for future in self.active_tasks.values():
                    try:
                        future.result(timeout=5)  # Wait up to 5 seconds
                    except Exception:
                        pass  # Task might have failed
            
            # Shutdown worker pool
            self.worker_pool.shutdown(wait=graceful)
            
            # Stop event loop
            if self.event_loop and self.event_loop.is_running():
                self.event_loop.call_soon_threadsafe(self.event_loop.stop)
            
            # Clear state
            self.task_queue.clear()
            self.active_tasks.clear()
            
            logger.info("HELENAKernel", "Shutdown completed")
            return True
            
        except Exception as e:
            logger.error("HELENAKernel", f"Shutdown failed: {e}")
            return False
    
    # Helper methods
    def _get_session_id(self) -> str:
        """Generate session ID"""
        return f"session_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    
    def _calculate_resource_budget(self, priority: TaskPriority) -> Dict[str, Any]:
        """Calculate resource budget based on priority"""
        # Base budgets (would be configurable)
        budgets = {
            TaskPriority.CRITICAL: {"cpu": 100, "ram_mb": 1024, "timeout": 30},
            TaskPriority.HIGH: {"cpu": 50, "ram_mb": 512, "timeout": 10},
            TaskPriority.NORMAL: {"cpu": 25, "ram_mb": 256, "timeout": 5},
            TaskPriority.LOW: {"cpu": 10, "ram_mb": 128, "timeout": 30},
            TaskPriority.BACKGROUND: {"cpu": 5, "ram_mb": 64, "timeout": 60},
        }
        
        return budgets.get(priority, budgets[TaskPriority.NORMAL]).copy()
    
    def _get_environmental_state(self) -> Dict[str, Any]:
        """Get current environmental state"""
        # This would collect real system data
        # For now, return placeholder
        return {
            "system_load": 0.0,
            "thermal_state": "normal",
            "power_status": "ac",
            "network_status": "disconnected",
            "time_of_day": time.strftime("%H:%M")
        }
    
    # Learning hooks
    def _learning_hook_memory(self, request: TaskRequest, result: TaskResult):
        """Learning hook for memory optimization"""
        if self.memory and result.status == TaskStatus.COMPLETED:
            # Extract patterns for memory storage
            memory_pattern = {
                "command": request.command,
                "parameters_hash": hashlib.md5(
                    json.dumps(request.parameters, sort_keys=True).encode()
                ).hexdigest(),
                "result_pattern": self._extract_result_pattern(result),
                "frequency": 1
            }
            
            # Store in memory system (would be implemented)
            logger.debug("HELENAKernel", "Memory learning hook executed")
    
    def _learning_hook_performance(self, request: TaskRequest, result: TaskResult):
        """Learning hook for performance optimization"""
        if result.performance_metrics:
            processing_time = result.performance_metrics.get("processing_time", 0)
            
            if processing_time > 0.5:  # Slow task
                # Record for optimization analysis
                logger.debug("HELENAKernel", 
                           f"Performance learning hook: slow task {request.task_id}")
    
    def _extract_result_pattern(self, result: TaskResult) -> Dict[str, Any]:
        """Extract pattern from result for learning"""
        # Simplified pattern extraction
        if isinstance(result.output, dict):
            return {
                "type": "dict",
                "keys": list(result.output.keys()),
                "size": len(str(result.output))
            }
        elif isinstance(result.output, str):
            return {
                "type": "string",
                "length": len(result.output),
                "lines": result.output.count('\n') + 1
            }
        else:
            return {"type": type(result.output).__name__}
