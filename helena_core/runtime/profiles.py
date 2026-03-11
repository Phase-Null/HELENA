# helena_core/runtime/profiles.py
"""
Performance profiles and mode switching
"""
import time
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
from collections import defaultdict

from .hardware import HardwareProfile
from .resources import ResourceManager, ResourceLimit, ResourceType

logger = logging.getLogger(__name__)

class PerformanceProfile(Enum):
    """Performance profile types"""
    IDLE = auto()           # Minimal resources, power saving
    BACKGROUND = auto()     # Gaming-safe, low resource usage
    NORMAL = auto()         # Standard operation
    DEFENSE = auto()        # High-performance for security
    TURBO = auto()          # Maximum performance (operator override)
    CUSTOM = auto()         # Custom operator-defined profile

@dataclass
class ProfileConfiguration:
    """Configuration for a performance profile"""
    name: str
    description: str
    cpu_limit_percent: float
    gpu_limit_percent: float
    ram_limit_mb: int
    vram_limit_mb: int
    thermal_target_c: float
    power_saving: bool
    network_priority: int  # 1-10, higher = more bandwidth
    disk_io_priority: int  # 1-10
    response_time_target_ms: int
    background_tasks_allowed: bool
    learning_enabled: bool
    
    # Dynamic adjustments
    auto_adjust: bool = True
    gaming_mode_auto: bool = True
    thermal_throttling: bool = True

class ProfileManager:
    """Manages performance profiles and automatic switching"""
    
    def __init__(self, 
                 resource_manager: ResourceManager,
                 hardware_profile: HardwareProfile):
        
        self.resource_manager = resource_manager
        self.hardware = hardware_profile
        
        # Current state
        self.current_profile: PerformanceProfile = PerformanceProfile.NORMAL
        self.previous_profile: Optional[PerformanceProfile] = None
        self.profile_lock = threading.RLock()
        
        # Profile configurations
        self.profiles: Dict[PerformanceProfile, ProfileConfiguration] = {}
        self._initialize_profiles()
        
        # Custom profiles
        self.custom_profiles: Dict[str, ProfileConfiguration] = {}
        
        # Profile history
        self.profile_history = []
        self.max_history = 100
        
        # Automatic switching
        self.auto_switch_enabled = True
        self.gaming_mode_enabled = False
        self.last_gaming_check = 0
        self.gaming_check_interval = 10  # seconds
        
        # Callbacks
        self.on_profile_change: Optional[Callable] = None
        self.on_gaming_detected: Optional[Callable] = None
        
        # Monitoring thread
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        
        logger.info("ProfileManager", "Profile manager initialized")
    
    def _initialize_profiles(self):
        """Initialize default performance profiles"""
        # Calculate hardware-based limits
        total_ram = self.hardware.memory.total_mb
        total_vram = sum(gpu.memory_total_mb for gpu in self.hardware.gpus)
        
        # IDLE profile - Minimal resources
        self.profiles[PerformanceProfile.IDLE] = ProfileConfiguration(
            name="Idle",
            description="Minimal resource usage for power saving",
            cpu_limit_percent=10.0,
            gpu_limit_percent=5.0,
            ram_limit_mb=int(total_ram * 0.1),  # 10% of RAM
            vram_limit_mb=int(total_vram * 0.1) if total_vram > 0 else 0,
            thermal_target_c=60.0,
            power_saving=True,
            network_priority=1,
            disk_io_priority=1,
            response_time_target_ms=5000,
            background_tasks_allowed=False,
            learning_enabled=False,
            auto_adjust=True,
            gaming_mode_auto=False
        )
        
        # BACKGROUND profile - Gaming-safe
        self.profiles[PerformanceProfile.BACKGROUND] = ProfileConfiguration(
            name="Background",
            description="Gaming-safe operation with minimal interference",
            cpu_limit_percent=25.0,
            gpu_limit_percent=15.0,
            ram_limit_mb=int(total_ram * 0.2),  # 20% of RAM
            vram_limit_mb=int(total_vram * 0.2) if total_vram > 0 else 0,
            thermal_target_c=70.0,
            power_saving=True,
            network_priority=2,
            disk_io_priority=2,
            response_time_target_ms=2000,
            background_tasks_allowed=True,
            learning_enabled=False,
            auto_adjust=True,
            gaming_mode_auto=True
        )
        
        # NORMAL profile - Standard operation
        self.profiles[PerformanceProfile.NORMAL] = ProfileConfiguration(
            name="Normal",
            description="Standard operation for daily tasks",
            cpu_limit_percent=85.0,
            gpu_limit_percent=50.0,
            ram_limit_mb=int(total_ram * 0.85),  # 85% of RAM
            vram_limit_mb=int(total_vram * 0.5) if total_vram > 0 else 0,
            thermal_target_c=75.0,
            power_saving=False,
            network_priority=5,
            disk_io_priority=5,
            response_time_target_ms=1000,
            background_tasks_allowed=True,
            learning_enabled=True,
            auto_adjust=True,
            gaming_mode_auto=True
        )
        
        # DEFENSE profile - High-performance security
        self.profiles[PerformanceProfile.DEFENSE] = ProfileConfiguration(
            name="Defense",
            description="Maximum performance for security operations",
            cpu_limit_percent=95.0,
            gpu_limit_percent=80.0,
            ram_limit_mb=int(total_ram * 0.9),  # 90% of RAM
            vram_limit_mb=int(total_vram * 0.8) if total_vram > 0 else 0,
            thermal_target_c=85.0,
            power_saving=False,
            network_priority=8,
            disk_io_priority=8,
            response_time_target_ms=500,
            background_tasks_allowed=False,
            learning_enabled=False,
            auto_adjust=False,
            gaming_mode_auto=False
        )
        
        # TURBO profile - Maximum performance
        self.profiles[PerformanceProfile.TURBO] = ProfileConfiguration(
            name="Turbo",
            description="Maximum performance (operator override)",
            cpu_limit_percent=95.0,
            gpu_limit_percent=95.0,
            ram_limit_mb=int(total_ram * 0.9),  # 90% of RAM
            vram_limit_mb=int(total_vram * 0.9) if total_vram > 0 else 0,
            thermal_target_c=90.0,
            power_saving=False,
            network_priority=10,
            disk_io_priority=10,
            response_time_target_ms=100,
            background_tasks_allowed=True,
            learning_enabled=True,
            auto_adjust=False,
            gaming_mode_auto=False
        )
    
    def start_monitoring(self):
        """Start profile monitoring and auto-switching"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="ProfileManager_Monitor"
        )
        self.monitoring_thread.start()
        
        logger.info("ProfileManager", "Profile monitoring started")
    
    def stop_monitoring(self):
        """Stop profile monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("ProfileManager", "Profile monitoring stopped")
    
    def _monitoring_loop(self):
        """Monitor system and auto-switch profiles"""
        while self.monitoring_active:
            try:
                # Check for gaming activity
                if self.auto_switch_enabled:
                    self._check_gaming_activity()
                
                # Check system load
                self._check_system_load()
                
                # Check thermal conditions
                self._check_thermal_conditions()
                
                # Apply profile adjustments
                self._apply_profile_adjustments()
                
                # Sleep
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error("ProfileManager", f"Monitoring loop error: {e}")
                time.sleep(10)  # Wait longer on error
    
    def _check_gaming_activity(self):
        """Check for gaming activity and switch to BACKGROUND if needed"""
        current_time = time.time()
        if current_time - self.last_gaming_check < self.gaming_check_interval:
            return
        
        self.last_gaming_check = current_time
        
        # Detect gaming (simplified - would be more sophisticated)
        is_gaming = self._detect_gaming()
        
        if is_gaming and not self.gaming_mode_enabled:
            # Gaming detected, switch to BACKGROUND if not already
            if self.current_profile != PerformanceProfile.BACKGROUND:
                config = self.profiles.get(self.current_profile)
                if config and config.gaming_mode_auto:
                    self.switch_profile(PerformanceProfile.BACKGROUND, reason="Gaming detected")
                    self.gaming_mode_enabled = True
                    
                    if self.on_gaming_detected:
                        self.on_gaming_detected(True)
        
        elif not is_gaming and self.gaming_mode_enabled:
            # Gaming ended, return to previous profile
            self.gaming_mode_enabled = False
            if self.previous_profile and self.previous_profile != PerformanceProfile.BACKGROUND:
                self.switch_profile(self.previous_profile, reason="Gaming ended")
            
            if self.on_gaming_detected:
                self.on_gaming_detected(False)
    
    def _detect_gaming(self) -> bool:
        """Detect if gaming is active"""
        # This is a simplified implementation
        # In production, would detect fullscreen applications, GPU usage patterns, etc.
        
        try:
            # Check for common gaming processes
            gaming_processes = [
                'steam', 'battle.net', 'origin', 'uplay', 'epicgames',
                'csgo', 'dota2', 'league of legends', 'valorant',
                'overwatch', 'minecraft', 'fortnite', 'call of duty'
            ]
            
            for proc in psutil.process_iter(['name']):
                try:
                    proc_name = proc.info['name'].lower()
                    if any(game in proc_name for game in gaming_processes):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Check for fullscreen applications (platform specific)
            # This would be platform-specific code
            
            # Check GPU usage pattern
            # High sustained GPU usage could indicate gaming
            
            return False
            
        except Exception:
            return False
    
    def _check_system_load(self):
        """Check system load and adjust profile if needed"""
        if not self.auto_switch_enabled:
            return
        
        current_profile = self.profiles.get(self.current_profile)
        if not current_profile or not current_profile.auto_adjust:
            return
        
        # Get current system usage
        usage = self.resource_manager.get_system_usage()
        
        # Check if we need to throttle due to high load
        if usage.cpu_percent > current_profile.cpu_limit_percent * 1.2:  # 20% over limit
            # Consider switching to a more restrictive profile
            if self.current_profile != PerformanceProfile.IDLE:
                self.switch_profile(
                    PerformanceProfile.IDLE, 
                    reason=f"High CPU load: {usage.cpu_percent:.1f}%"
                )
        
        # Check RAM usage
        ram_percent = (usage.ram_mb / self.hardware.memory.total_mb) * 100
        if ram_percent > 90:  # Critical RAM usage
            self.switch_profile(
                PerformanceProfile.IDLE,
                reason=f"Critical RAM usage: {ram_percent:.1f}%"
            )
    
    def _check_thermal_conditions(self):
        """Check thermal conditions and adjust profile"""
        usage = self.resource_manager.get_system_usage()
        current_profile = self.profiles.get(self.current_profile)
        
        if not current_profile or not current_profile.thermal_throttling:
            return
        
        # Check CPU temperature
        if usage.cpu_temp_c and usage.cpu_temp_c > current_profile.thermal_target_c:
            # Temperature exceeded target
            if self.current_profile != PerformanceProfile.IDLE:
                self.switch_profile(
                    PerformanceProfile.IDLE,
                    reason=f"High CPU temperature: {usage.cpu_temp_c:.1f}°C"
                )
        
        # Check GPU temperature
        if usage.gpu_temp_c and usage.gpu_temp_c > current_profile.thermal_target_c:
            if self.current_profile != PerformanceProfile.IDLE:
                self.switch_profile(
                    PerformanceProfile.IDLE,
                    reason=f"High GPU temperature: {usage.gpu_temp_c:.1f}°C"
                )
    
    def _apply_profile_adjustments(self):
        """Apply current profile's resource limits"""
        current_profile = self.profiles.get(self.current_profile)
        if not current_profile:
            return
        
        # Convert profile to resource limits
        limits = self._profile_to_limits(current_profile)
        self.resource_manager.set_limits(limits)
    
    def _profile_to_limits(self, profile: ProfileConfiguration) -> List[ResourceLimit]:
        """Convert profile configuration to resource limits"""
        limits = []
        
        # CPU limit
        limits.append(ResourceLimit(
            resource_type=ResourceType.CPU,
            max_usage=profile.cpu_limit_percent,
            priority=1,
            action='throttle'
        ))
        
        # RAM limit
        limits.append(ResourceLimit(
            resource_type=ResourceType.RAM,
            max_usage=(profile.ram_limit_mb / self.hardware.memory.total_mb) * 100,
            priority=1,
            action='suspend'
        ))
        
        # Thermal limit
        limits.append(ResourceLimit(
            resource_type=ResourceType.THERMAL,
            max_usage=profile.thermal_target_c,
            priority=0,  # Highest priority
            action='throttle'
        ))
        
        # GPU limit (if GPU available)
        if any(gpu.memory_total_mb > 0 for gpu in self.hardware.gpus):
            limits.append(ResourceLimit(
                resource_type=ResourceType.GPU,
                max_usage=profile.gpu_limit_percent,
                priority=2,
                action='throttle'
            ))
        
        return limits
    
    def switch_profile(self, 
                      new_profile: PerformanceProfile,
                      reason: str = "Manual switch") -> bool:
        """Switch to a new performance profile"""
        with self.profile_lock:
            if new_profile not in self.profiles and new_profile != PerformanceProfile.CUSTOM:
                logger.error("ProfileManager", f"Unknown profile: {new_profile}")
                return False
            
            if new_profile == self.current_profile:
                return True  # Already in this profile
            
            # Store previous profile
            self.previous_profile = self.current_profile
            
            # Update current profile
            self.current_profile = new_profile
            
            # Record in history
            self.profile_history.append({
                'timestamp': time.time(),
                'from': self.previous_profile.name if self.previous_profile else None,
                'to': new_profile.name,
                'reason': reason
            })
            
            # Keep history manageable
            if len(self.profile_history) > self.max_history:
                self.profile_history.pop(0)
            
            # Apply profile adjustments
            self._apply_profile_adjustments()
            
            # Log the switch
            logger.info("ProfileManager", 
                       f"Switched profile: {self.previous_profile.name if self.previous_profile else 'None'} "
                       f"-> {new_profile.name} ({reason})")
            
            # Notify callback
            if self.on_profile_change:
                self.on_profile_change(self.previous_profile, new_profile, reason)
            
            return True
    
    def get_current_profile(self) -> Optional[ProfileConfiguration]:
        """Get current profile configuration"""
        if self.current_profile == PerformanceProfile.CUSTOM:
            # Return first custom profile (in production, would track which custom profile)
            if self.custom_profiles:
                return next(iter(self.custom_profiles.values()))
            return None
        
        return self.profiles.get(self.current_profile)
    
    def create_custom_profile(self, 
                             name: str,
                             configuration: ProfileConfiguration) -> bool:
        """Create a custom performance profile"""
        if name in self.custom_profiles:
            logger.warning("ProfileManager", f"Custom profile '{name}' already exists")
            return False
        
        self.custom_profiles[name] = configuration
        
        # Create a profile entry for switching
        profile_id = PerformanceProfile.CUSTOM
        
        logger.info("ProfileManager", f"Created custom profile: {name}")
        return True
    
    def update_custom_profile(self, 
                             name: str,
                             **kwargs) -> bool:
        """Update an existing custom profile"""
        if name not in self.custom_profiles:
            return False
        
        profile = self.custom_profiles[name]
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        logger.info("ProfileManager", f"Updated custom profile: {name}")
        return True
    
    def delete_custom_profile(self, name: str) -> bool:
        """Delete a custom profile"""
        if name in self.custom_profiles:
            del self.custom_profiles[name]
            logger.info("ProfileManager", f"Deleted custom profile: {name}")
            return True
        return False
    
    def get_available_profiles(self) -> List[Dict[str, Any]]:
        """Get list of available profiles"""
        profiles = []
        
        # Standard profiles
        for profile_enum, config in self.profiles.items():
            profiles.append({
                'id': profile_enum.name,
                'name': config.name,
                'description': config.description,
                'type': 'standard',
                'current': profile_enum == self.current_profile
            })
        
        # Custom profiles
        for name, config in self.custom_profiles.items():
            profiles.append({
                'id': f"CUSTOM_{name}",
                'name': f"Custom: {name}",
                'description': config.description,
                'type': 'custom',
                'current': False  # Custom profiles need special handling
            })
        
        return profiles
    
    def get_profile_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get profile switch history"""
        return self.profile_history[-limit:] if limit else self.profile_history.copy()
    
    def get_profile_statistics(self) -> Dict[str, Any]:
        """Get profile management statistics"""
        # Calculate time spent in each profile
        profile_times = defaultdict(float)
        last_time = None
        last_profile = None
        
        for entry in self.profile_history:
            if last_time and last_profile:
                duration = entry['timestamp'] - last_time
                profile_times[last_profile] += duration
            
            last_time = entry['timestamp']
            last_profile = entry['to']
        
        # Add current session
        if last_time:
            current_duration = time.time() - last_time
            profile_times[last_profile] += current_duration
        
        return {
            'current_profile': self.current_profile.name,
            'auto_switch_enabled': self.auto_switch_enabled,
            'gaming_mode_active': self.gaming_mode_enabled,
            'total_switches': len(self.profile_history),
            'profile_times': dict(profile_times),
            'custom_profiles_count': len(self.custom_profiles)
        }
    
    def export_profile(self, 
                      profile_enum: PerformanceProfile) -> Optional[Dict[str, Any]]:
        """Export a profile configuration"""
        if profile_enum == PerformanceProfile.CUSTOM:
            return None
        
        config = self.profiles.get(profile_enum)
        if not config:
            return None
        
        return {
            'id': profile_enum.name,
            'configuration': {
                'name': config.name,
                'description': config.description,
                'cpu_limit_percent': config.cpu_limit_percent,
                'gpu_limit_percent': config.gpu_limit_percent,
                'ram_limit_mb': config.ram_limit_mb,
                'vram_limit_mb': config.vram_limit_mb,
                'thermal_target_c': config.thermal_target_c,
                'power_saving': config.power_saving,
                'network_priority': config.network_priority,
                'disk_io_priority': config.disk_io_priority,
                'response_time_target_ms': config.response_time_target_ms,
                'background_tasks_allowed': config.background_tasks_allowed,
                'learning_enabled': config.learning_enabled,
                'auto_adjust': config.auto_adjust,
                'gaming_mode_auto': config.gaming_mode_auto,
                'thermal_throttling': config.thermal_throttling
            }
        }
    
    def import_profile(self, 
                      profile_data: Dict[str, Any]) -> bool:
        """Import a profile configuration"""
        try:
            profile_id = profile_data['id']
            config_data = profile_data['configuration']
            
            # Check if it's a standard profile
            try:
                profile_enum = PerformanceProfile[profile_id]
                
                # Update existing profile
                config = self.profiles[profile_enum]
                for key, value in config_data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                
                logger.info("ProfileManager", f"Imported standard profile: {profile_id}")
                return True
                
            except KeyError:
                # It's a custom profile
                if profile_id.startswith('CUSTOM_'):
                    name = profile_id[7:]  # Remove 'CUSTOM_' prefix
                    
                    # Create ProfileConfiguration
                    config = ProfileConfiguration(**config_data)
                    self.custom_profiles[name] = config
                    
                    logger.info("ProfileManager", f"Imported custom profile: {name}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error("ProfileManager", f"Failed to import profile: {e}")
            return False

