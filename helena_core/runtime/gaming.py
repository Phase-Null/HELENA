# helena_core/runtime/gaming.py
"""
Gaming compatibility and automatic optimization
"""
import time
import threading
import psutil
import sys
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

class GamingDetectionMethod(Enum):
    """Methods for detecting gaming activity"""
    PROCESS_NAME = auto()
    WINDOW_TITLE = auto()
    GPU_USAGE = auto()
    INPUT_DEVICES = auto()
    AUDIO_ACTIVITY = auto()
    NETWORK_TRAFFIC = auto()

@dataclass
class GameProfile:
    """Profile for a specific game"""
    name: str
    process_names: List[str]
    window_titles: List[str]
    gpu_intensive: bool = True
    cpu_priority: int = 3  # 1-10, higher = more CPU for game
    memory_reservation_mb: int = 0
    optimize_network: bool = True
    suspend_helena_modules: List[str] = field(default_factory=list)
    recommended_profile: str = "background"
    
    # Performance hints
    prefers_fullscreen: bool = True
    frame_rate_target: Optional[int] = None
    vram_usage_mb: Optional[int] = None

@dataclass
class GamingSession:
    """Active gaming session"""
    game: GameProfile
    detected_time: float
    process_ids: Set[int]
    performance_impact: float = 0.0  # 0-1 scale
    suspended_modules: List[str] = field(default_factory=list)
    original_profile: Optional[str] = None

class GamingOptimizer:
    """Optimizes HELENA for gaming compatibility"""
    
    def __init__(self, 
                 profile_manager,
                 resource_manager,
                 module_manager=None):
        
        self.profile_manager = profile_manager
        self.resource_manager = resource_manager
        self.module_manager = module_manager
        
        # Game database
        self.game_profiles: Dict[str, GameProfile] = {}
        self._load_default_game_profiles()
        
        # Active state
        self.active_session: Optional[GamingSession] = None
        self.detection_enabled = True
        self.auto_optimize = True
        
        # Detection thresholds
        self.detection_thresholds = {
            'gpu_usage_min': 50.0,  # Minimum GPU usage to consider gaming
            'cpu_usage_min': 30.0,  # Minimum CPU usage
            'process_lifetime_min': 10.0,  # Minimum seconds process has been running
            'confidence_threshold': 0.35,  # Confidence score to trigger detection
        }
        
        # Monitoring
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.check_interval = 5.0  # seconds
        
        # Statistics
        self.detection_history = []
        self.optimization_history = []
        
        # Callbacks
        self.on_game_detected: Optional[Callable] = None
        self.on_game_ended: Optional[Callable] = None
        self.on_optimization_applied: Optional[Callable] = None
        
        logger.info("GamingOptimizer", "Gaming optimizer initialized")
    
    def _load_default_game_profiles(self):
        """Load default game profiles"""
        # Popular games
        self.game_profiles['steam'] = GameProfile(
            name="Steam Client",
            process_names=["steam.exe", "steam", "Steam"],
            window_titles=["Steam"],
            gpu_intensive=False,
            cpu_priority=2,
            optimize_network=True,
            recommended_profile="background"
        )
        
        self.game_profiles['csgo'] = GameProfile(
            name="Counter-Strike: Global Offensive",
            process_names=["csgo.exe", "csgo"],
            window_titles=["Counter-Strike"],
            gpu_intensive=True,
            cpu_priority=8,
            memory_reservation_mb=2048,
            optimize_network=True,
            suspend_helena_modules=["training", "background_analysis"],
            recommended_profile="background"
        )
        
        self.game_profiles['minecraft'] = GameProfile(
            name="Minecraft",
            process_names=["javaw.exe", "minecraft", "Minecraft"],
            window_titles=["Minecraft"],
            gpu_intensive=True,
            cpu_priority=6,
            memory_reservation_mb=4096,
            optimize_network=False,
            suspend_helena_modules=["training"],
            recommended_profile="background"
        )
        
        self.game_profiles['valorant'] = GameProfile(
            name="VALORANT",
            process_names=["valorant.exe", "VALORANT"],
            window_titles=["VALORANT"],
            gpu_intensive=True,
            cpu_priority=9,
            memory_reservation_mb=3072,
            optimize_network=True,
            suspend_helena_modules=["training", "security_scanning", "background_analysis"],
            recommended_profile="background"
        )
        
        # Game launchers
        self.game_profiles['battlenet'] = GameProfile(
            name="Battle.net",
            process_names=["battle.net.exe", "Battle.net"],
            window_titles=["Battle.net"],
            gpu_intensive=False,
            cpu_priority=3,
            optimize_network=True,
            recommended_profile="background"
        )
        
        self.game_profiles['epicgames'] = GameProfile(
            name="Epic Games Launcher",
            process_names=["epicgameslauncher.exe", "EpicGamesLauncher"],
            window_titles=["Epic Games"],
            gpu_intensive=False,
            cpu_priority=2,
            optimize_network=True,
            recommended_profile="background"
        )
    
    def start_monitoring(self):
        """Start gaming detection monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="GamingOptimizer_Monitor"
        )
        self.monitoring_thread.start()
        
        logger.info("GamingOptimizer", "Gaming monitoring started")
    
    def stop_monitoring(self):
        """Stop gaming detection"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        # Clean up any active session
        if self.active_session:
            self._end_gaming_session()
        
        logger.info("GamingOptimizer", "Gaming monitoring stopped")
    
    def _monitoring_loop(self):
        """Monitor for gaming activity"""
        while self.monitoring_active:
            try:
                if self.detection_enabled:
                    self._check_for_gaming()
                
                if self.active_session and self.auto_optimize:
                    self._optimize_for_gaming()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error("GamingOptimizer", f"Monitoring loop error: {e}")
                time.sleep(10)
    
    def _check_for_gaming(self):
        """Check for gaming activity"""
        if self.active_session:
            # Check if game is still running
            if not self._is_game_still_running():
                self._end_gaming_session()
            return
        
        # Detect new games
        detected_games = self._detect_running_games()
        
        if detected_games:
            # Start session with the most confident detection
            best_game = max(detected_games, key=lambda x: x['confidence'])
            
            game_profile = best_game['profile']
            process_ids = best_game['process_ids']
            
            self._start_gaming_session(game_profile, process_ids)
    
    def _detect_running_games(self) -> List[Dict[str, Any]]:
        """Detect currently running games"""
        detected = []
        
        try:
            # Scan all processes
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                try:
                    proc_info = proc.info
                    pid = proc_info['pid']
                    name = proc_info['name'].lower() if proc_info['name'] else ''
                    create_time = proc_info['create_time']
                    
                    # Skip short-lived processes
                    if time.time() - create_time < self.detection_thresholds['process_lifetime_min']:
                        continue
                    
                    # Check against game profiles
                    for game_id, profile in self.game_profiles.items():
                        confidence = 0.0
                        matched_methods = []
                        
                        # Check process names
                        for proc_name in profile.process_names:
                            if proc_name.lower() in name:
                                confidence += 0.4
                                matched_methods.append(GamingDetectionMethod.PROCESS_NAME)
                                break
                        
                        # Check window titles (would require platform-specific code)
                        # This is simplified
                        
                        # If we have reasonable confidence, record detection
                        if confidence >= self.detection_thresholds['confidence_threshold']:
                            detected.append({
                                'game_id': game_id,
                                'profile': profile,
                                'process_ids': {pid},
                                'confidence': confidence,
                                'methods': matched_methods
                            })
                            break
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            logger.error("GamingOptimizer", f"Game detection failed: {e}")
        
        return detected
    
    def _is_game_still_running(self) -> bool:
        """Check if the current game is still running"""
        if not self.active_session:
            return False
        
        try:
            # Check if any of the game processes are still running
            for pid in self.active_session.process_ids:
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        return True
                except psutil.NoSuchProcess:
                    continue
            
            return False
            
        except Exception:
            return False
    
    def _start_gaming_session(self, 
                             game_profile: GameProfile,
                             process_ids: Set[int]):
        """Start a new gaming session"""
        logger.info("GamingOptimizer", f"Game detected: {game_profile.name}")
        
        # Store original profile
        current_profile = self.profile_manager.get_current_profile()
        original_profile = current_profile.name if current_profile else None
        
        # Create session
        session = GamingSession(
            game=game_profile,
            detected_time=time.time(),
            process_ids=process_ids,
            original_profile=original_profile
        )
        
        self.active_session = session
        
        # Record detection
        self.detection_history.append({
            'timestamp': time.time(),
            'game': game_profile.name,
            'process_ids': list(process_ids),
            'original_profile': original_profile
        })
        
        # Apply optimizations
        if self.auto_optimize:
            self._apply_game_optimizations(session)
        
        # Switch to recommended profile
        try:
            from .profiles import PerformanceProfile
            profile_enum = PerformanceProfile[game_profile.recommended_profile.upper()]
            self.profile_manager.switch_profile(
                profile_enum,
                reason=f"Gaming: {game_profile.name}"
            )
        except (KeyError, AttributeError):
            # Fallback to BACKGROUND
            self.profile_manager.switch_profile(
                PerformanceProfile.BACKGROUND,
                reason=f"Gaming: {game_profile.name}"
            )
        
        # Notify callback
        if self.on_game_detected:
            self.on_game_detected(game_profile, session)
    
    def _apply_game_optimizations(self, session: GamingSession):
        """Apply optimizations for the game"""
        optimizations_applied = []
        
        # Suspend HELENA modules
        if self.module_manager and session.game.suspend_helena_modules:
            for module_name in session.game.suspend_helena_modules:
                try:
                    self.module_manager.suspend_module(module_name)
                    session.suspended_modules.append(module_name)
                    optimizations_applied.append(f"suspend_module:{module_name}")
                except Exception as e:
                    logger.warning("GamingOptimizer", f"Failed to suspend module {module_name}: {e}")
        
        # Adjust process priorities for game processes
        for pid in session.process_ids:
            try:
                proc = psutil.Process(pid)
                if sys.platform == "win32":
                    proc.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                else:
                    current_nice = proc.nice()
                    target_nice = max(-10, current_nice - session.game.cpu_priority)
                    proc.nice(target_nice)
                
                optimizations_applied.append(f"priority:{pid}")
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.warning(f"GamingOptimizer: Failed to adjust priority for PID {pid}: {e}")
        
        # Reserve memory if specified
        if session.game.memory_reservation_mb > 0:
            # This would be implemented with memory management
            pass
        
        # Record optimizations
        self.optimization_history.append({
            'timestamp': time.time(),
            'game': session.game.name,
            'optimizations': optimizations_applied
        })
        
        # Notify callback
        if self.on_optimization_applied:
            self.on_optimization_applied(session.game, optimizations_applied)
        
        logger.info("GamingOptimizer", 
                   f"Applied {len(optimizations_applied)} optimizations for {session.game.name}")
    
    def _optimize_for_gaming(self):
        """Continuously optimize for active gaming session"""
        if not self.active_session:
            return
        
        try:
            # Monitor performance impact
            usage = self.resource_manager.get_system_usage()
            
            # Calculate performance impact
            impact = self._calculate_performance_impact(usage)
            self.active_session.performance_impact = impact
            
            # Adjust optimizations based on impact
            if impact > 0.8:  # High impact
                self._apply_aggressive_optimizations()
            elif impact < 0.3:  # Low impact
                self._relax_optimizations()
                
        except Exception as e:
            logger.error("GamingOptimizer", f"Optimization monitoring failed: {e}")
    
    def _calculate_performance_impact(self, usage) -> float:
        """Calculate gaming performance impact (0-1 scale)"""
        impact = 0.0
        
        # High CPU usage reduces gaming performance
        if usage.cpu_percent > 80:
            impact += 0.4
        elif usage.cpu_percent > 60:
            impact += 0.2
        
        # High RAM usage
        total_ram = self.resource_manager.hardware.memory.total_mb
        if total_ram > 0:
            ram_percent = (usage.ram_mb / total_ram) * 100
            if ram_percent > 90:
                impact += 0.4
            elif ram_percent > 75:
                impact += 0.2
        
        # High temperatures
        if usage.cpu_temp_c and usage.cpu_temp_c > 85:
            impact += 0.2
        
        return min(impact, 1.0)
    
    def _apply_aggressive_optimizations(self):
        """Apply more aggressive optimizations"""
        if not self.active_session or not self.module_manager:
            return
        
        # Suspend additional non-critical modules
        non_critical_modules = ["documentation_generator", "code_analysis", "background_training"]
        
        for module_name in non_critical_modules:
            if module_name not in self.active_session.suspended_modules:
                try:
                    self.module_manager.suspend_module(module_name)
                    self.active_session.suspended_modules.append(module_name)
                    logger.debug("GamingOptimizer", f"Aggressively suspended: {module_name}")
                except Exception:
                    pass
    
    def _relax_optimizations(self):
        """Relax optimizations when impact is low"""
        if not self.active_session or not self.module_manager:
            return
        
        # Only resume modules that weren't explicitly suspended by game profile
        game_suspended = set(self.active_session.game.suspend_helena_modules)
        
        for module_name in self.active_session.suspended_modules.copy():
            if module_name not in game_suspended:
                try:
                    self.module_manager.resume_module(module_name)
                    self.active_session.suspended_modules.remove(module_name)
                    logger.debug("GamingOptimizer", f"Resumed: {module_name}")
                except Exception:
                    pass
    
    def _end_gaming_session(self):
        """End the current gaming session"""
        if not self.active_session:
            return
        
        logger.info("GamingOptimizer", f"Game ended: {self.active_session.game.name}")
        
        # Restore original profile
        if self.active_session.original_profile:
            try:
                from .profiles import PerformanceProfile
                profile_enum = PerformanceProfile[self.active_session.original_profile.upper()]
                self.profile_manager.switch_profile(
                    profile_enum,
                    reason="Gaming session ended"
                )
            except (KeyError, AttributeError):
                # Fallback to NORMAL
                self.profile_manager.switch_profile(
                    PerformanceProfile.NORMAL,
                    reason="Gaming session ended"
                )
        
        # Resume suspended modules
        if self.module_manager and self.active_session.suspended_modules:
            for module_name in self.active_session.suspended_modules:
                try:
                    self.module_manager.resume_module(module_name)
                except Exception as e:
                    logger.warning("GamingOptimizer", f"Failed to resume module {module_name}: {e}")
        
        # Restore process priorities
        for pid in self.active_session.process_ids:
            try:
                proc = psutil.Process(pid)
                # Reset to default nice value
                if sys.platform == "win32":
                    proc.nice(psutil.NORMAL_PRIORITY_CLASS)
                else:
                    proc.nice(0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.warning(f"GamingOptimizer: Failed to restore priority for PID {pid}: {e}")
        
        # Notify callback
        if self.on_game_ended:
            self.on_game_ended(self.active_session)
        
        # Clear session
        self.active_session = None
    
    def add_game_profile(self, profile: GameProfile) -> bool:
        """Add a custom game profile"""
        if profile.name.lower() in self.game_profiles:
            logger.warning("GamingOptimizer", f"Game profile '{profile.name}' already exists")
            return False
        
        self.game_profiles[profile.name.lower()] = profile
        logger.info("GamingOptimizer", f"Added game profile: {profile.name}")
        return True
    
    def remove_game_profile(self, game_name: str) -> bool:
        """Remove a game profile"""
        if game_name.lower() in self.game_profiles:
            del self.game_profiles[game_name.lower()]
            logger.info("GamingOptimizer", f"Removed game profile: {game_name}")
            return True
        return False
    
    def get_game_profile(self, game_name: str) -> Optional[GameProfile]:
        """Get a game profile by name"""
        return self.game_profiles.get(game_name.lower())
    
    def get_active_session(self) -> Optional[Dict[str, Any]]:
        """Get information about active gaming session"""
        if not self.active_session:
            return None
        
        return {
            'game': self.active_session.game.name,
            'detected_time': self.active_session.detected_time,
            'duration': time.time() - self.active_session.detected_time,
            'process_ids': list(self.active_session.process_ids),
            'performance_impact': self.active_session.performance_impact,
            'suspended_modules': self.active_session.suspended_modules,
            'original_profile': self.active_session.original_profile
        }
    
    def get_detection_statistics(self) -> Dict[str, Any]:
        """Get gaming detection statistics"""
        return {
            'monitoring_active': self.monitoring_active,
            'detection_enabled': self.detection_enabled,
            'auto_optimize': self.auto_optimize,
            'active_session': self.active_session is not None,
            'game_profiles_count': len(self.game_profiles),
            'detection_history_count': len(self.detection_history),
            'optimization_history_count': len(self.optimization_history),
            'recent_detections': self.detection_history[-10:] if self.detection_history else []
        }
    
    def manual_game_start(self, game_name: str) -> bool:
        """Manually start gaming optimization for a game"""
        profile = self.get_game_profile(game_name)
        if not profile:
            logger.error("GamingOptimizer", f"No profile found for game: {game_name}")
            return False
        
        # Find running process
        process_ids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                for game_proc in profile.process_names:
                    if game_proc.lower() in proc_name:
                        process_ids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not process_ids:
            logger.warning("GamingOptimizer", f"No running processes found for {game_name}")
            return False
        
        self._start_gaming_session(profile, process_ids)
        return True
    
    def manual_game_end(self):
        """Manually end current gaming session"""
        if self.active_session:
            self._end_gaming_session()
            return True
        return False
    
    def export_game_profile(self, game_name: str) -> Optional[Dict[str, Any]]:
        """Export a game profile"""
        profile = self.get_game_profile(game_name)
        if not profile:
            return None
        
        return {
            'name': profile.name,
            'process_names': profile.process_names,
            'window_titles': profile.window_titles,
            'gpu_intensive': profile.gpu_intensive,
            'cpu_priority': profile.cpu_priority,
            'memory_reservation_mb': profile.memory_reservation_mb,
            'optimize_network': profile.optimize_network,
            'suspend_helena_modules': profile.suspend_helena_modules,
            'recommended_profile': profile.recommended_profile,
            'prefers_fullscreen': profile.prefers_fullscreen,
            'frame_rate_target': profile.frame_rate_target,
            'vram_usage_mb': profile.vram_usage_mb
        }
    
    def import_game_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Import a game profile"""
        try:
            profile = GameProfile(**profile_data)
            return self.add_game_profile(profile)
        except Exception as e:
            logger.error("GamingOptimizer", f"Failed to import game profile: {e}")
            return False

