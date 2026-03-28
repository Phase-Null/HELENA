# helena_core/runtime/__init__.py
"""
HELENA Runtime Layer
"""
from .hardware import (
    HardwareDetector,
    HardwareProfile,
    CPUInfo,
    GPUInfo,
    MemoryInfo,
    StorageInfo,
    ThermalInfo,
    ProcessorArchitecture,
    GPUPlatform,
    get_hardware_detector
)
from .resources import (
    ResourceManager,
    ResourceLimit,
    ResourceUsage,
    ResourceType,
    ProcessInfo,
    ThrottleAction
)
from .profiles import (
    ProfileManager,
    PerformanceProfile,
    ProfileConfiguration
)
from .gaming import (
    GamingOptimizer,
    GameProfile,
    GamingSession,
    GamingDetectionMethod
)
from typing import Any

from ..utils.logging import get_logger

logger = get_logger()


def _cfg_get(config: Any, key: str, default: Any = None) -> Any:
    """Read a value from a dict-like or object-like config."""
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)

__all__ = [
    # Hardware
    "HardwareDetector",
    "HardwareProfile",
    "CPUInfo",
    "GPUInfo",
    "MemoryInfo",
    "StorageInfo",
    "ThermalInfo",
    "ProcessorArchitecture",
    "GPUPlatform",
    "get_hardware_detector",
    
    # Resources
    "ResourceManager",
    "ResourceLimit",
    "ResourceUsage",
    "ResourceType",
    "ProcessInfo",
    "ThrottleAction",
    
    # Profiles
    "ProfileManager",
    "PerformanceProfile",
    "ProfileConfiguration",
    
    # Gaming
    "GamingOptimizer",
    "GameProfile",
    "GamingSession",
    "GamingDetectionMethod",
]

class HELENARuntime:
    """
    Main runtime coordinator for HELENA
    """
    
    def __init__(self, config_manager):
        self.config = config_manager
        
        # Initialize components
        self.hardware = get_hardware_detector()
        self.hardware_profile = self.hardware.detect()
        
        self.resource_manager = ResourceManager(self.hardware_profile)
        self.profile_manager = ProfileManager(self.resource_manager, self.hardware_profile)
        self.gaming_optimizer = GamingOptimizer(self.profile_manager, self.resource_manager)
        
        # Runtime state
        self.initialized = False
        self.operational = False
        
        # Configuration
        self._load_configuration()
        
        logger.info("HELENARuntime", "Runtime layer initialized")
    
    def _load_configuration(self):
        """Load runtime configuration"""
        try:
            perf_config = self.config.get_section("performance")
            
            # Configure profile manager
            if perf_config:
               self.profile_manager.auto_switch_enabled = bool(
                   _cfg_get(perf_config, "auto_throttle", True)
               )
               self.gaming_optimizer.auto_optimize = bool(
                   _cfg_get(perf_config, "gaming_mode_auto", True)
               )
                
            logger.debug("HELENARuntime", "Runtime configuration loaded")
            
        except Exception as e:
            logger.error("HELENARuntime", f"Failed to load runtime config: {e}")
    
    def initialize(self) -> bool:
        """Initialize runtime layer"""
        try:
            # Start resource monitoring
            self.resource_manager.start_monitoring()
            
            # Start profile monitoring
            self.profile_manager.start_monitoring()
            
            # Start gaming optimization
            self.gaming_optimizer.start_monitoring()
            
            # Set up callbacks
            self._setup_callbacks()
            
            self.initialized = True
            self.operational = True
            
            logger.info("HELENARuntime", "Runtime layer fully operational")
            return True
            
        except Exception as e:
            logger.error("HELENARuntime", f"Runtime initialization failed: {e}")
            return False
    
    def _setup_callbacks(self):
        """Setup runtime callbacks"""
        # Resource limit violations
        self.resource_manager.on_limit_violation = self._handle_resource_violation
        
        # Thermal warnings
        self.resource_manager.on_thermal_warning = self._handle_thermal_warning
        
        # Profile changes
        self.profile_manager.on_profile_change = self._handle_profile_change
        
        # Gaming events
        self.gaming_optimizer.on_game_detected = self._handle_game_detected
        self.gaming_optimizer.on_game_ended = self._handle_game_ended
    
    def _handle_resource_violation(self, violation):
        """Handle resource limit violation"""
        logger.warning("HELENARuntime", 
                      f"Resource violation: {violation['limit'].resource_type.name} "
                      f"({violation['current_value']:.1f} > {violation['max_value']:.1f})")
    
    def _handle_thermal_warning(self, warning):
        """Handle thermal warning"""
        logger.warning("HELENARuntime",
                      f"Thermal {warning['level']}: {warning['type']} "
                      f"({warning['temperature']:.1f}°C)")
    
    def _handle_profile_change(self, old_profile, new_profile, reason):
        """Handle profile change"""
        logger.info("HELENARuntime",
                   f"Profile changed: {old_profile.name if old_profile else 'None'} "
                   f"-> {new_profile.name} ({reason})")
    
    def _handle_game_detected(self, game_profile, session):
        """Handle game detection"""
        logger.info("HELENARuntime",
                   f"Game detected: {game_profile.name}, "
                   f"switching to {game_profile.recommended_profile} profile")
    
    def _handle_game_ended(self, session):
        """Handle game ending"""
        logger.info("HELENARuntime",
                   f"Game ended: {session.game.name}, "
                   f"restoring normal operation")
    
    def switch_profile(self, profile_name: str) -> bool:
        """Switch performance profile"""
        try:
            from .profiles import PerformanceProfile
            profile_enum = PerformanceProfile[profile_name.upper()]
            return self.profile_manager.switch_profile(profile_enum, "Operator request")
        except KeyError:
            logger.error("HELENARuntime", f"Unknown profile: {profile_name}")
            return False
    
    def get_current_profile(self) -> dict[str, Any]:
        """Get current profile information"""
        profile = self.profile_manager.get_current_profile()
        if not profile:
            return {}
        
        return {
            'name': profile.name,
            'description': profile.description,
            'limits': {
                'cpu_percent': profile.cpu_limit_percent,
                'gpu_percent': profile.gpu_limit_percent,
                'ram_mb': profile.ram_limit_mb,
                'vram_mb': profile.vram_limit_mb
            },
            'settings': {
                'power_saving': profile.power_saving,
                'auto_adjust': profile.auto_adjust,
                'thermal_throttling': profile.thermal_throttling
            }
        }
    
    def get_system_status(self) -> dict[str, Any]:
        """Get complete system status"""
        usage = self.resource_manager.get_system_usage()
        
        return {
            'hardware': self.hardware.get_hardware_summary(),
            'resources': {
                'cpu_percent': usage.cpu_percent,
                'ram_mb': usage.ram_mb,
                'ram_percent': (usage.ram_mb / self.hardware_profile.memory.total_mb * 100) 
                              if self.hardware_profile.memory.total_mb > 0 else 0,
                'cpu_temp_c': usage.cpu_temp_c,
                'gpu_temp_c': usage.gpu_temp_c
            },
            'profile': self.get_current_profile(),
            'gaming': {
                'active': self.gaming_optimizer.active_session is not None,
                'game': self.gaming_optimizer.active_session.game.name 
                       if self.gaming_optimizer.active_session else None
            },
            'statistics': {
                'resource_manager': self.resource_manager.get_statistics(),
                'profile_manager': self.profile_manager.get_profile_statistics(),
                'gaming_optimizer': self.gaming_optimizer.get_detection_statistics()
            }
        }
    
    def get_resource_history(self, 
                           hours: int = 1,
                           resource_type: str = "cpu") -> list[dict[str, Any]]:
        """Get resource usage history"""
        try:
            from .resources import ResourceType
            type_enum = ResourceType[resource_type.upper()]
            
            # Calculate how many data points we need
            points_needed = hours * 3600 // self.resource_manager.update_interval
            return self.resource_manager.get_usage_history(points_needed, type_enum)
            
        except KeyError:
            logger.error("HELENARuntime", f"Unknown resource type: {resource_type}")
            return []
    
    def set_resource_limits(self, limits: list[dict[str, Any]]) -> bool:
        """Set custom resource limits"""
        try:
            from .resources import ResourceLimit, ResourceType
            
            resource_limits = []
            for limit_data in limits:
                limit = ResourceLimit(
                    resource_type=ResourceType[limit_data['type'].upper()],
                    max_usage=limit_data['max_usage'],
                    priority=limit_data.get('priority', 1),
                    action=limit_data.get('action', 'throttle'),
                    cooldown_seconds=limit_data.get('cooldown_seconds', 60.0)
                )
                resource_limits.append(limit)
            
            self.resource_manager.set_limits(resource_limits)
            logger.info("HELENARuntime", f"Set {len(resource_limits)} custom limits")
            return True
            
        except Exception as e:
            logger.error("HELENARuntime", f"Failed to set resource limits: {e}")
            return False
    
    def create_custom_profile(self, 
                            name: str,
                            configuration: dict[str, Any]) -> bool:
        """Create a custom performance profile"""
        try:
            from .profiles import ProfileConfiguration
            
            profile_config = ProfileConfiguration(
                name=name,
                description=configuration.get('description', 'Custom profile'),
                cpu_limit_percent=configuration['cpu_limit_percent'],
                gpu_limit_percent=configuration['gpu_limit_percent'],
                ram_limit_mb=configuration['ram_limit_mb'],
                vram_limit_mb=configuration.get('vram_limit_mb', 0),
                thermal_target_c=configuration.get('thermal_target_c', 75.0),
                power_saving=configuration.get('power_saving', False),
                network_priority=configuration.get('network_priority', 5),
                disk_io_priority=configuration.get('disk_io_priority', 5),
                response_time_target_ms=configuration.get('response_time_target_ms', 1000),
                background_tasks_allowed=configuration.get('background_tasks_allowed', True),
                learning_enabled=configuration.get('learning_enabled', True)
            )
            
            return self.profile_manager.create_custom_profile(name, profile_config)
            
        except Exception as e:
            logger.error("HELENARuntime", f"Failed to create custom profile: {e}")
            return False
    
    def shutdown(self, graceful: bool = True) -> bool:
        """Shutdown runtime layer"""
        try:
            logger.info("HELENARuntime", "Shutting down runtime layer...")
            
            # Stop gaming optimization
            self.gaming_optimizer.stop_monitoring()
            
            # Stop profile monitoring
            self.profile_manager.stop_monitoring()
            
            # Stop resource monitoring
            self.resource_manager.stop_monitoring()
            
            self.operational = False
            
            logger.info("HELENARuntime", "Runtime layer shutdown complete")
            return True
            
        except Exception as e:
            logger.error("HELENARuntime", f"Runtime shutdown failed: {e}")
            return False
    
    def emergency_throttle(self) -> dict[str, Any]:
        """Emergency throttle - maximum resource reduction"""
        # Switch to IDLE profile
        self.switch_profile("IDLE")
        
        # Suspend all non-critical processes
        self.resource_manager.suspend_processes(ResourceType.CPU)
        
        return {
            'action': 'emergency_throttle',
            'profile': 'IDLE',
            'message': 'Maximum resource reduction applied'
        }

