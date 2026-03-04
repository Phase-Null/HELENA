# helena_core/runtime/resources.py
"""
Resource management and throttling system
"""
import time
import threading
import psutil
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
from collections import deque

from .hardware import get_hardware_detector, HardwareProfile

logger = logging.getLogger(__name__)

class ResourceType(Enum):
    """Types of system resources"""
    CPU = auto()
    GPU = auto()
    RAM = auto()
    VRAM = auto()
    DISK_IO = auto()
    NETWORK_IO = auto()
    THERMAL = auto()

@dataclass
class ResourceLimit:
    """Resource limit configuration"""
    resource_type: ResourceType
    max_usage: float  # Percentage or absolute value
    priority: int  # Lower number = higher priority
    action: str  # 'throttle', 'suspend', 'kill'
    cooldown_seconds: float = 60.0

@dataclass
class ResourceUsage:
    """Current resource usage"""
    cpu_percent: float = 0.0
    gpu_percent: float = 0.0
    ram_mb: int = 0
    vram_mb: int = 0
    disk_io_mbps: float = 0.0
    network_io_mbps: float = 0.0
    cpu_temp_c: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class ProcessInfo:
    """Information about a managed process"""
    pid: int
    name: str
    resource_usage: ResourceUsage
    priority: int
    managed: bool = True
    suspended: bool = False
    last_updated: float = field(default_factory=time.time)

class ThrottleAction(Enum):
    """Types of throttle actions"""
    NONE = auto()
    REDUCE_CPU = auto()
    REDUCE_GPU = auto()
    SUSPEND_PROCESS = auto()
    TERMINATE_PROCESS = auto()
    REDUCE_PRIORITY = auto()

class ResourceManager:
    """Manages system resources and enforces limits"""
    
    def __init__(self, hardware_profile: Optional[HardwareProfile] = None):
        self.hardware = hardware_profile or get_hardware_detector().detect()
        
        # Resource tracking
        self.system_usage = ResourceUsage()
        self.processes: Dict[int, ProcessInfo] = {}
        self.usage_history = deque(maxlen=1000)
        
        # Thermal thresholds – MUST come before _create_default_limits()
        self.thermal_thresholds = {
            'cpu_warning': 80.0,  # °C
            'cpu_critical': 95.0,  # °C
            'gpu_warning': 85.0,  # °C
            'gpu_critical': 100.0,  # °C
            'system_warning': 70.0,  # °C
            'system_critical': 85.0,  # °C
        }
        
        # Limits configuration
        self.limits: List[ResourceLimit] = []
        self.default_limits = self._create_default_limits()
        
        # Throttle actions
        self.active_throttles: Dict[int, List[ThrottleAction]] = {}
        self.throttle_cooldowns: Dict[int, float] = {}
        
        # Monitoring thread
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.update_interval = 1.0  # seconds
        
        # Callbacks
        self.on_limit_violation: Optional[Callable] = None
        self.on_thermal_warning: Optional[Callable] = None
        self.on_resource_update: Optional[Callable] = None
        
        logger.info("ResourceManager", "Resource manager initialized")
    
    def _create_default_limits(self) -> List[ResourceLimit]:
        """Create default resource limits"""
        return [
            ResourceLimit(
                resource_type=ResourceType.CPU,
                max_usage=80.0,  # 80% CPU usage
                priority=1,
                action='throttle'
            ),
            ResourceLimit(
                resource_type=ResourceType.RAM,
                max_usage=90.0,  # 90% RAM usage
                priority=1,
                action='suspend'
            ),
            ResourceLimit(
                resource_type=ResourceType.THERMAL,
                max_usage=self.thermal_thresholds['cpu_critical'],
                priority=0,  # Highest priority
                action='throttle'
            ),
            ResourceLimit(
                resource_type=ResourceType.VRAM,
                max_usage=95.0,  # 95% VRAM usage
                priority=2,
                action='throttle'
            ),
        ]
    
    def start_monitoring(self):
        """Start resource monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="ResourceManager_Monitor"
        )
        self.monitoring_thread.start()
        
        logger.info("ResourceManager", "Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("ResourceManager", "Resource monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Update system usage
                self._update_system_usage()
                
                # Update process usage
                self._update_process_usage()
                
                # Check limits
                violations = self._check_limits()
                if violations:
                    self._handle_violations(violations)
                
                # Check thermal
                thermal_warnings = self._check_thermal()
                if thermal_warnings and self.on_thermal_warning:
                    for warning in thermal_warnings:
                        self.on_thermal_warning(warning)
                
                # Notify update
                if self.on_resource_update:
                    self.on_resource_update(self.system_usage)
                
                # Store history
                self.usage_history.append(self.system_usage)
                
                # Sleep
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error("ResourceManager", f"Monitoring loop error: {e}")
                time.sleep(5)  # Wait before retry
    
    def _update_system_usage(self):
        """Update system-wide resource usage"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            disk_io_mbps = 0.0
            if disk_io:
                # Calculate MB/s from bytes
                disk_io_mbps = (disk_io.read_bytes + disk_io.write_bytes) / (1024 * 1024)
            
            # Network I/O
            net_io = psutil.net_io_counters()
            network_io_mbps = 0.0
            if net_io:
                network_io_mbps = (net_io.bytes_sent + net_io.bytes_recv) / (1024 * 1024)
            
            # GPU usage (if available)
            gpu_percent = 0.0
            vram_mb = 0
            
            # Thermal
            cpu_temp = None
            gpu_temp = None
            
            # Get temperatures if available
            try:
                if hasattr(psutil, 'sensors_temperatures'):
                    temps = psutil.sensors_temperatures()
                    if temps and 'coretemp' in temps:
                        for entry in temps['coretemp']:
                            if 'Core' in entry.label:
                                cpu_temp = entry.current
                                break
            except Exception:
                pass
            
            self.system_usage = ResourceUsage(
                cpu_percent=cpu_percent,
                gpu_percent=gpu_percent,
                ram_mb=memory.used // (1024 * 1024),
                vram_mb=vram_mb,
                disk_io_mbps=disk_io_mbps,
                network_io_mbps=network_io_mbps,
                cpu_temp_c=cpu_temp,
                gpu_temp_c=gpu_temp,
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.error("ResourceManager", f"Failed to update system usage: {e}")
    
    def _update_process_usage(self):
        """Update resource usage for managed processes"""
        processes_to_remove = []
        
        for pid, process_info in list(self.processes.items()):
            try:
                process = psutil.Process(pid)
                
                # Check if process still exists
                if not process.is_running():
                    processes_to_remove.append(pid)
                    continue
                
                # Update usage
                with process.oneshot():
                    cpu_percent = process.cpu_percent()
                    memory_info = process.memory_info()
                    
                    # Get GPU usage if available (would need platform-specific code)
                    gpu_percent = 0.0
                    
                    process_info.resource_usage = ResourceUsage(
                        cpu_percent=cpu_percent,
                        gpu_percent=gpu_percent,
                        ram_mb=memory_info.rss // (1024 * 1024),
                        timestamp=time.time()
                    )
                    process_info.last_updated = time.time()
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                processes_to_remove.append(pid)
            except Exception as e:
                logger.warning("ResourceManager", f"Failed to update process {pid}: {e}")
        
        # Remove dead processes
        for pid in processes_to_remove:
            self._remove_process(pid)
    
    def _check_limits(self) -> List[Dict[str, Any]]:
        """Check for resource limit violations"""
        violations = []
        
        for limit in self.limits + self.default_limits:
            current_value = self._get_current_resource_value(limit.resource_type)
            max_value = limit.max_usage
            
            if current_value > max_value:
                violations.append({
                    'limit': limit,
                    'current_value': current_value,
                    'max_value': max_value,
                    'exceedance': ((current_value - max_value) / max_value) * 100
                })
        
        return violations
    
    def _get_current_resource_value(self, resource_type: ResourceType) -> float:
        """Get current value for a resource type"""
        if resource_type == ResourceType.CPU:
            return self.system_usage.cpu_percent
        elif resource_type == ResourceType.RAM:
            total_memory = self.hardware.memory.total_mb
            if total_memory > 0:
                return (self.system_usage.ram_mb / total_memory) * 100
            return 0.0
        elif resource_type == ResourceType.GPU:
            return self.system_usage.gpu_percent
        elif resource_type == ResourceType.VRAM:
            total_vram = sum(gpu.memory_total_mb for gpu in self.hardware.gpus)
            if total_vram > 0:
                return (self.system_usage.vram_mb / total_vram) * 100
            return 0.0
        elif resource_type == ResourceType.THERMAL:
            # Return highest temperature
            temps = []
            if self.system_usage.cpu_temp_c:
                temps.append(self.system_usage.cpu_temp_c)
            if self.system_usage.gpu_temp_c:
                temps.append(self.system_usage.gpu_temp_c)
            return max(temps) if temps else 0.0
        elif resource_type == ResourceType.DISK_IO:
            return self.system_usage.disk_io_mbps
        elif resource_type == ResourceType.NETWORK_IO:
            return self.system_usage.network_io_mbps
        
        return 0.0
    
    def _handle_violations(self, violations: List[Dict[str, Any]]):
        """Handle resource limit violations"""
        # Sort by priority (lower number = higher priority)
        violations.sort(key=lambda v: v['limit'].priority)
        
        for violation in violations:
            limit = violation['limit']
            
            # Check cooldown
            limit_key = f"{limit.resource_type.name}_{limit.priority}"
            if limit_key in self.throttle_cooldowns:
                if time.time() - self.throttle_cooldowns[limit_key] < limit.cooldown_seconds:
                    continue  # Still in cooldown
            
            # Execute action
            action_result = self._execute_limit_action(limit, violation)
            
            if action_result:
                # Set cooldown
                self.throttle_cooldowns[limit_key] = time.time()
                
                # Notify violation
                if self.on_limit_violation:
                    violation['action_taken'] = action_result
                    self.on_limit_violation(violation)
                
                logger.warning("ResourceManager",
                              f"Limit violation: {limit.resource_type.name} "
                              f"({violation['current_value']:.1f} > {limit.max_usage:.1f}), "
                              f"action: {limit.action}")
    
    def _execute_limit_action(self, 
                             limit: ResourceLimit,
                             violation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute action for limit violation"""
        if limit.action == 'throttle':
            return self._throttle_processes(limit.resource_type)
        elif limit.action == 'suspend':
            return self._suspend_processes(limit.resource_type)
        elif limit.action == 'kill':
            return self._kill_processes(limit.resource_type)
        
        return None
    
    def _throttle_processes(self, resource_type: ResourceType) -> Dict[str, Any]:
        """Throttle processes consuming the resource"""
        throttled = []
        
        # Sort processes by resource usage
        process_list = []
        for pid, process_info in self.processes.items():
            if not process_info.managed or process_info.suspended:
                continue
            
            usage = self._get_process_resource_usage(process_info, resource_type)
            if usage > 0:
                process_list.append((pid, process_info, usage))
        
        # Sort by usage (highest first)
        process_list.sort(key=lambda x: x[2], reverse=True)
        
        # Throttle top offenders
        for pid, process_info, usage in process_list[:3]:  # Top 3
            try:
                action = self._throttle_single_process(pid, process_info, resource_type)
                if action:
                    throttled.append({
                        'pid': pid,
                        'name': process_info.name,
                        'action': action.name,
                        'resource_usage': usage
                    })
                    
                    # Track active throttle
                    if pid not in self.active_throttles:
                        self.active_throttles[pid] = []
                    self.active_throttles[pid].append(action)
                    
            except Exception as e:
                logger.error("ResourceManager", f"Failed to throttle process {pid}: {e}")
        
        return {
            'action': 'throttle',
            'resource_type': resource_type.name,
            'throttled_processes': throttled
        }
    
    def _get_process_resource_usage(self, 
                                   process_info: ProcessInfo,
                                   resource_type: ResourceType) -> float:
        """Get process usage for specific resource"""
        if resource_type == ResourceType.CPU:
            return process_info.resource_usage.cpu_percent
        elif resource_type == ResourceType.RAM:
            return process_info.resource_usage.ram_mb
        elif resource_type == ResourceType.GPU:
            return process_info.resource_usage.gpu_percent
        
        return 0.0
    
    def _throttle_single_process(self,
                                pid: int,
                                process_info: ProcessInfo,
                                resource_type: ResourceType) -> Optional[ThrottleAction]:
        """Throttle a single process"""
        try:
            process = psutil.Process(pid)
            
            if resource_type == ResourceType.CPU:
                # Reduce CPU affinity or priority
                current_nice = process.nice()
                if current_nice < 10:  # Don't go too low
                    process.nice(current_nice + 1)
                    return ThrottleAction.REDUCE_CPU
                    
            elif resource_type == ResourceType.RAM:
                # Can't directly limit RAM, but can reduce priority
                current_nice = process.nice()
                if current_nice < 15:
                    process.nice(current_nice + 2)
                    return ThrottleAction.REDUCE_PRIORITY
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            logger.error("ResourceManager", f"Failed to throttle process {pid}: {e}")
        
        return None
    
    def _suspend_processes(self, resource_type: ResourceType) -> Dict[str, Any]:
        """Suspend processes consuming the resource"""
        suspended = []
        
        # Get processes sorted by usage
        process_list = []
        for pid, process_info in self.processes.items():
            if not process_info.managed or process_info.suspended:
                continue
            
            usage = self._get_process_resource_usage(process_info, resource_type)
            if usage > 0:
                process_list.append((pid, process_info, usage))
        
        process_list.sort(key=lambda x: x[2], reverse=True)
        
        # Suspend top offenders
        for pid, process_info, usage in process_list[:2]:  # Top 2
            try:
                process = psutil.Process(pid)
                process.suspend()
                
                process_info.suspended = True
                suspended.append({
                    'pid': pid,
                    'name': process_info.name,
                    'resource_usage': usage
                })
                
                logger.warning("ResourceManager", f"Suspended process {pid} ({process_info.name})")
                
            except Exception as e:
                logger.error("ResourceManager", f"Failed to suspend process {pid}: {e}")
        
        return {
            'action': 'suspend',
            'resource_type': resource_type.name,
            'suspended_processes': suspended
        }
    
    def _kill_processes(self, resource_type: ResourceType) -> Dict[str, Any]:
        """Kill processes consuming the resource"""
        killed = []
        
        # Only kill non-critical, managed processes
        for pid, process_info in list(self.processes.items()):
            if not process_info.managed or process_info.priority < 5:  # Don't kill high priority
                continue
            
            usage = self._get_process_resource_usage(process_info, resource_type)
            if usage > 0:
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    
                    # Wait a bit
                    try:
                        process.wait(timeout=2)
                    except psutil.TimeoutExpired:
                        process.kill()
                    
                    killed.append({
                        'pid': pid,
                        'name': process_info.name,
                        'resource_usage': usage
                    })
                    
                    # Remove from tracking
                    self._remove_process(pid)
                    
                    logger.warning("ResourceManager", f"Killed process {pid} ({process_info.name})")
                    
                except Exception as e:
                    logger.error("ResourceManager", f"Failed to kill process {pid}: {e}")
        
        return {
            'action': 'kill',
            'resource_type': resource_type.name,
            'killed_processes': killed
        }
    
    def _check_thermal(self) -> List[Dict[str, Any]]:
        """Check for thermal warnings"""
        warnings = []
        
        # Check CPU temperature
        if self.system_usage.cpu_temp_c:
            if self.system_usage.cpu_temp_c >= self.thermal_thresholds['cpu_critical']:
                warnings.append({
                    'type': 'cpu_temperature',
                    'level': 'critical',
                    'temperature': self.system_usage.cpu_temp_c,
                    'threshold': self.thermal_thresholds['cpu_critical']
                })
            elif self.system_usage.cpu_temp_c >= self.thermal_thresholds['cpu_warning']:
                warnings.append({
                    'type': 'cpu_temperature',
                    'level': 'warning',
                    'temperature': self.system_usage.cpu_temp_c,
                    'threshold': self.thermal_thresholds['cpu_warning']
                })
        
        # Check GPU temperature
        if self.system_usage.gpu_temp_c:
            if self.system_usage.gpu_temp_c >= self.thermal_thresholds['gpu_critical']:
                warnings.append({
                    'type': 'gpu_temperature',
                    'level': 'critical',
                    'temperature': self.system_usage.gpu_temp_c,
                    'threshold': self.thermal_thresholds['gpu_critical']
                })
            elif self.system_usage.gpu_temp_c >= self.thermal_thresholds['gpu_warning']:
                warnings.append({
                    'type': 'gpu_temperature',
                    'level': 'warning',
                    'temperature': self.system_usage.gpu_temp_c,
                    'threshold': self.thermal_thresholds['gpu_warning']
                })
        
        return warnings
    
    def register_process(self, 
                        pid: int,
                        name: str,
                        priority: int = 10,
                        managed: bool = True) -> bool:
        """Register a process for resource management"""
        try:
            process = psutil.Process(pid)
            if not process.is_running():
                return False
            
            # Get initial usage
            with process.oneshot():
                cpu_percent = process.cpu_percent()
                memory_info = process.memory_info()
            
            process_info = ProcessInfo(
                pid=pid,
                name=name,
                resource_usage=ResourceUsage(
                    cpu_percent=cpu_percent,
                    ram_mb=memory_info.rss // (1024 * 1024),
                    timestamp=time.time()
                ),
                priority=priority,
                managed=managed
            )
            
            self.processes[pid] = process_info
            logger.debug("ResourceManager", f"Registered process {pid} ({name})")
            
            return True
            
        except Exception as e:
            logger.error("ResourceManager", f"Failed to register process {pid}: {e}")
            return False
    
    def unregister_process(self, pid: int) -> bool:
        """Unregister a process from resource management"""
        if pid in self.processes:
            del self.processes[pid]
            
            # Remove any active throttles
            if pid in self.active_throttles:
                del self.active_throttles[pid]
            
            logger.debug("ResourceManager", f"Unregistered process {pid}")
            return True
        
        return False
    
    def _remove_process(self, pid: int):
        """Remove a process (internal)"""
        if pid in self.processes:
            del self.processes[pid]
        if pid in self.active_throttles:
            del self.active_throttles[pid]
    
    def resume_suspended_processes(self) -> List[int]:
        """Resume all suspended processes"""
        resumed = []
        
        for pid, process_info in self.processes.items():
            if process_info.suspended:
                try:
                    process = psutil.Process(pid)
                    process.resume()
                    process_info.suspended = False
                    resumed.append(pid)
                    
                    logger.info("ResourceManager", f"Resumed process {pid}")
                    
                except Exception as e:
                    logger.error("ResourceManager", f"Failed to resume process {pid}: {e}")
        
        return resumed
    
    def set_limits(self, limits: List[ResourceLimit]):
        """Set custom resource limits"""
        self.limits = limits.copy()
        logger.info("ResourceManager", f"Set {len(limits)} custom limits")
    
    def add_limit(self, limit: ResourceLimit):
        """Add a single resource limit"""
        self.limits.append(limit)
    
    def clear_limits(self):
        """Clear custom limits (use defaults)"""
        self.limits.clear()
    
    def get_system_usage(self) -> ResourceUsage:
        """Get current system resource usage"""
        return self.system_usage
    
    def get_process_usage(self, pid: int) -> Optional[ResourceUsage]:
        """Get resource usage for a specific process"""
        if pid in self.processes:
            return self.processes[pid].resource_usage
        return None
    
    def get_usage_history(self, 
                         limit: int = 100,
                         resource_type: Optional[ResourceType] = None) -> List[Dict[str, Any]]:
        """Get usage history"""
        history = list(self.usage_history)[-limit:]
        
        if resource_type:
            return [
                {
                    'timestamp': usage.timestamp,
                    'value': self._extract_resource_value(usage, resource_type),
                    'usage': usage
                }
                for usage in history
            ]
        else:
            return [
                {
                    'timestamp': usage.timestamp,
                    'cpu_percent': usage.cpu_percent,
                    'ram_mb': usage.ram_mb,
                    'gpu_percent': usage.gpu_percent
                }
                for usage in history
            ]
    
    def _extract_resource_value(self, 
                               usage: ResourceUsage,
                               resource_type: ResourceType) -> float:
        """Extract specific resource value from usage"""
        if resource_type == ResourceType.CPU:
            return usage.cpu_percent
        elif resource_type == ResourceType.RAM:
            return usage.ram_mb
        elif resource_type == ResourceType.GPU:
            return usage.gpu_percent
        elif resource_type == ResourceType.VRAM:
            return usage.vram_mb
        elif resource_type == ResourceType.DISK_IO:
            return usage.disk_io_mbps
        elif resource_type == ResourceType.NETWORK_IO:
            return usage.network_io_mbps
        elif resource_type == ResourceType.THERMAL:
            return usage.cpu_temp_c or 0.0
        
        return 0.0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get resource management statistics"""
        return {
            'monitoring_active': self.monitoring_active,
            'processes_managed': len([p for p in self.processes.values() if p.managed]),
            'processes_suspended': len([p for p in self.processes.values() if p.suspended]),
            'active_throttles': sum(len(actions) for actions in self.active_throttles.values()),
            'limits_active': len(self.limits) + len(self.default_limits),
            'usage_history_size': len(self.usage_history),
            'current_usage': {
                'cpu_percent': self.system_usage.cpu_percent,
                'ram_mb': self.system_usage.ram_mb,
                'ram_percent': (self.system_usage.ram_mb / self.hardware.memory.total_mb * 100) 
                              if self.hardware.memory.total_mb > 0 else 0
            }
        }
