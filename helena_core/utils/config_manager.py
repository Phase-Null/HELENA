# helena_core/utils/config_manager.py
"""
Centralized configuration management with encryption and validation
"""
import os
import yaml
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)

class ConfigSection(Enum):
    """Configuration sections"""
    SYSTEM = "system"
    PERFORMANCE = "performance"
    MEMORY = "memory"
    SECURITY = "security"
    NETWORK = "network"
    PERSONALITY = "personality"
    TRAINING = "training"
    MODULES = "modules"

@dataclass
class SystemConfig:
    """System-level configuration"""
    name: str = "HELENA"
    version: str = "1.0.0"
    operator_id: str = "primary_operator"
    log_level: str = "INFO"
    data_directory: str = "./helena_data"
    temp_directory: str = "./helena_temp"
    max_log_size_mb: int = 100
    log_retention_days: int = 30
    
@dataclass
class PerformanceConfig:
    """Performance configuration"""
    default_profile: str = "normal"
    auto_throttle: bool = True
    gaming_mode_auto: bool = True
    cpu_idle_threshold: float = 30.0  # Percent
    thermal_threshold: float = 85.0   # Celsius
    response_time_target_ms: int = 1000
    
    # Resource limits
    cpu_limit_normal: float = 50.0    # Percent
    cpu_limit_background: float = 25.0
    cpu_limit_turbo: float = 80.0
    
    ram_limit_normal_mb: int = 4096
    ram_limit_background_mb: int = 2048
    ram_limit_turbo_mb: int = 8192
    
@dataclass  
class MemoryConfig:
    """Memory system configuration"""
    vector_dimension: int = 768
    max_working_memories: int = 1000
    max_short_term_memories: int = 100000
    cache_size: int = 1000
    embedding_model: str = "all-MiniLM-L6-v2"
    similarity_threshold: float = 0.7
    auto_cleanup_interval_hours: int = 24
    
@dataclass
class SecurityConfig:
    """Security configuration"""
    encryption_enabled: bool = True
    encryption_algorithm: str = "AES-256-GCM"
    require_validation: bool = True
    max_unauthorized_attempts: int = 5
    sandbox_enabled: bool = True
    network_require_approval: bool = True
    kill_switch_hardware_token: Optional[str] = None
    
@dataclass
class PersonalityConfig:
    """Personality configuration"""
    verbosity: float = 0.4            # 0-1 scale
    technical_depth: float = 0.8
    humor_threshold: float = 0.7
    creativity_level: float = 0.6
    formality_level: float = 0.8
    response_style: str = "concise_technical"
    
@dataclass
class TrainingConfig:
    """Training system configuration"""
    enabled: bool = False
    max_training_hours: float = 2.0
    scheduled_time: str = "02:00"     # 2 AM
    focus_areas: list = field(default_factory=lambda: ["code_quality", "efficiency"])
    max_parameter_change: float = 0.1  # 10%
    require_operator_approval: bool = True
    
@dataclass
class ModuleConfig:
    """Module system configuration"""
    sandbox_default: bool = True
    max_cpu_percent: float = 25.0
    max_memory_mb: int = 512
    network_access_default: bool = False
    filesystem_access_default: str = "sandbox_only"
    require_digital_signature: bool = True
    
@dataclass
class HelenaConfig:
    """Complete HELENA configuration"""
    system: SystemConfig = field(default_factory=SystemConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    modules: ModuleConfig = field(default_factory=ModuleConfig)
    
    # Runtime state (not saved)
    _encryption_key: Optional[bytes] = None
    _config_hash: Optional[str] = None
    _loaded_path: Optional[Path] = None

class ConfigManager:
    """Manages HELENA configuration with encryption and validation"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / ".helena" / "config"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.config = HelenaConfig()
        self.fernet = None
        
        # Default hardware profiles path
        self.hardware_profiles_path = Path(__file__).parent.parent / "config" / "hardware_profiles.yaml"
        self.security_policies_path = Path(__file__).parent.parent / "config" / "security_policies.yaml"
        
    def initialize(self, operator_id: str, encryption_key: Optional[bytes] = None) -> bool:
        """
        Initialize configuration system
        Returns: True if successful
        """
        try:
            # Set operator ID
            self.config.system.operator_id = operator_id
            
            # Generate or set encryption key
            if encryption_key:
                self.config._encryption_key = encryption_key
            elif self.config.security.encryption_enabled:
                self.config._encryption_key = self._generate_encryption_key(operator_id)
            
            # Initialize encryption
            if self.config._encryption_key:
                self.fernet = Fernet(self._derive_fernet_key(self.config._encryption_key))
            
            # Load or create config
            if self.config_path.exists():
                loaded = self.load()
                if not loaded:
                    logger.warning("Failed to load config, creating default")
                    return self._create_default_config()
                return True
            else:
                return self._create_default_config()
                
        except Exception as e:
            logger.error(f"Failed to initialize config: {e}")
            return False
    
    def _create_default_config(self) -> bool:
        """Create default configuration file"""
        try:
            # Detect hardware and apply profile
            hardware_profile = self._detect_hardware_profile()
            self._apply_hardware_profile(hardware_profile)
            
            # Save config
            return self.save()
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")
            return False
    
    def _detect_hardware_profile(self) -> str:
        """Detect hardware and return appropriate profile name"""
        try:
            import psutil
            cpu_cores = psutil.cpu_count(logical=False)
            total_ram = psutil.virtual_memory().total / (1024**3)  # GB
            
            # Simple profile detection
            if total_ram < 8:
                return "minimal"
            elif total_ram < 16:
                return "standard"
            elif total_ram < 32:
                return "performance"
            else:
                return "workstation"
                
        except Exception:
            return "standard"
    
    def _apply_hardware_profile(self, profile_name: str):
        """Apply hardware-specific configuration"""
        try:
            if self.hardware_profiles_path.exists():
                with open(self.hardware_profiles_path, 'r') as f:
                    profiles = yaml.safe_load(f)
                
                profile = profiles.get(profile_name, {})
                
                # Apply profile settings
                if "performance" in profile:
                    perf = profile["performance"]
                    self.config.performance.cpu_limit_normal = perf.get("cpu_limit_normal", 50.0)
                    self.config.performance.ram_limit_normal_mb = perf.get("ram_limit_normal_mb", 4096)
                
                if "memory" in profile:
                    mem = profile["memory"]
                    self.config.memory.max_working_memories = mem.get("max_working_memories", 1000)
                    self.config.memory.max_short_term_memories = mem.get("max_short_term_memories", 100000)
                    
                logger.info(f"Applied hardware profile: {profile_name}")
                
        except Exception as e:
            logger.warning(f"Failed to apply hardware profile: {e}")
    
    def load(self) -> bool:
        """Load configuration from encrypted file"""
        try:
            if not self.config_path.exists():
                return False
            
            with open(self.config_path, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt if encryption enabled
            if self.config.security.encryption_enabled and self.fernet:
                try:
                    decrypted_data = self.fernet.decrypt(encrypted_data)
                    config_dict = yaml.safe_load(decrypted_data.decode('utf-8'))
                except Exception as e:
                    logger.error(f"Failed to decrypt config: {e}")
                    return False
            else:
                config_dict = yaml.safe_load(encrypted_data.decode('utf-8'))
            
            # Update config object
            self._update_from_dict(config_dict)
            
            # Store hash for change detection
            self.config._config_hash = self._calculate_config_hash()
            self.config._loaded_path = self.config_path
            
            logger.info("Configuration loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return False
    
    def save(self) -> bool:
        """Save configuration to encrypted file"""
        try:
            # Convert config to dict
            config_dict = self._to_dict()
            
            # Serialize to YAML
            yaml_data = yaml.dump(config_dict, default_flow_style=False)
            
            # Encrypt if enabled
            if self.config.security.encryption_enabled and self.fernet:
                encrypted_data = self.fernet.encrypt(yaml_data.encode('utf-8'))
            else:
                encrypted_data = yaml_data.encode('utf-8')
            
            # Create backup if file exists
            if self.config_path.exists():
                backup_path = self.config_path.with_suffix('.bak')
                import shutil
                shutil.copy2(self.config_path, backup_path)
            
            # Write to file
            with open(self.config_path, 'wb') as f:
                f.write(encrypted_data)
            
            # Update hash
            self.config._config_hash = self._calculate_config_hash()
            
            logger.info("Configuration saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    def get_section(self, section) -> Any:
        """Get configuration section. Accepts ConfigSection enum or string name."""
        section_map = {
            ConfigSection.SYSTEM: self.config.system,
            ConfigSection.PERFORMANCE: self.config.performance,
            ConfigSection.MEMORY: self.config.memory,
            ConfigSection.SECURITY: self.config.security,
            ConfigSection.PERSONALITY: self.config.personality,
            ConfigSection.TRAINING: self.config.training,
            ConfigSection.MODULES: self.config.modules,
        }
        # Support string lookups (callers often pass "training", "memory", etc.)
        if isinstance(section, str):
            section_upper = section.upper()
            for cs in ConfigSection:
                if cs.name == section_upper or cs.value == section.lower():
                    section = cs
                    break
            else:
                return None
        return section_map.get(section)
    
    def update_section(self, section: ConfigSection, updates: Dict[str, Any]) -> bool:
        """Update configuration section"""
        try:
            section_obj = self.get_section(section)
            if not section_obj:
                return False
            
            # Update fields
            for key, value in updates.items():
                if hasattr(section_obj, key):
                    setattr(section_obj, key, value)
            
            # Save changes
            return self.save()
            
        except Exception as e:
            logger.error(f"Failed to update config section: {e}")
            return False
    
    def validate(self) -> Dict[str, List[str]]:
        """Validate configuration, return errors by section"""
        errors = {}
        
        # System validation
        system_errors = []
        if not self.config.system.operator_id or len(self.config.system.operator_id) < 3:
            system_errors.append("Operator ID must be at least 3 characters")
        if self.config.system.max_log_size_mb < 10:
            system_errors.append("Max log size must be at least 10MB")
        if system_errors:
            errors["system"] = system_errors
        
        # Performance validation
        perf_errors = []
        if not 0 <= self.config.performance.cpu_limit_normal <= 100:
            perf_errors.append("CPU limit must be between 0 and 100")
        if self.config.performance.ram_limit_normal_mb < 512:
            perf_errors.append("RAM limit must be at least 512MB")
        if perf_errors:
            errors["performance"] = perf_errors
        
        # Security validation
        sec_errors = []
        if self.config.security.encryption_enabled and not self.config._encryption_key:
            sec_errors.append("Encryption enabled but no key set")
        if sec_errors:
            errors["security"] = sec_errors
        
        return errors
    
    def get_encryption_key(self) -> Optional[bytes]:
        """Get encryption key (handle with care)"""
        return self.config._encryption_key
    
    def reset_to_defaults(self, keep_operator_id: bool = True) -> bool:
        """Reset configuration to defaults"""
        try:
            operator_id = self.config.system.operator_id if keep_operator_id else "primary_operator"
            
            # Create new config
            self.config = HelenaConfig()
            self.config.system.operator_id = operator_id
            
            # Re-initialize
            return self.initialize(operator_id, self.config._encryption_key)
            
        except Exception as e:
            logger.error(f"Failed to reset config: {e}")
            return False
    
    def export_config(self, export_path: Path, include_secrets: bool = False) -> bool:
        """Export configuration to file"""
        try:
            config_dict = self._to_dict()
            
            # Remove sensitive data if requested
            if not include_secrets:
                if "_encryption_key" in config_dict:
                    del config_dict["_encryption_key"]
                if "security" in config_dict:
                    if "kill_switch_hardware_token" in config_dict["security"]:
                        del config_dict["security"]["kill_switch_hardware_token"]
            
            with open(export_path, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            return False
    
    def _generate_encryption_key(self, operator_id: str) -> bytes:
        """Generate encryption key from operator ID and system entropy"""
        import secrets
        
        # Use operator ID as salt
        salt = operator_id.encode('utf-8')
        
        # Generate random component
        random_component = secrets.token_bytes(32)
        
        # Combine with deterministic component from operator ID
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        deterministic_component = kdf.derive(operator_id.encode('utf-8'))
        
        # XOR combine for final key
        key = bytes(a ^ b for a, b in zip(random_component, deterministic_component))
        
        return key
    
    def _derive_fernet_key(self, encryption_key: bytes) -> bytes:
        """Derive Fernet key from encryption key"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'helena_fernet_salt',
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(encryption_key))
    
    def _to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary, excluding runtime attributes"""
        config_dict = {}
        
        # Convert each dataclass section
        for field_name in self.config.__dataclass_fields__:
            if field_name.startswith('_'):
                continue  # Skip private fields
            
            field_value = getattr(self.config, field_name)
            if hasattr(field_value, '__dataclass_fields__'):
                # It's a dataclass
                config_dict[field_name] = asdict(field_value)
            else:
                config_dict[field_name] = field_value
        
        return config_dict
    
    def _update_from_dict(self, config_dict: Dict[str, Any]):
        """Update config from dictionary"""
        for section_name, section_data in config_dict.items():
            if hasattr(self.config, section_name):
                section_obj = getattr(self.config, section_name)
                
                if hasattr(section_obj, '__dataclass_fields__'):
                    # Update dataclass fields
                    for field_name, field_value in section_data.items():
                        if hasattr(section_obj, field_name):
                            setattr(section_obj, field_name, field_value)
                else:
                    # Direct attribute
                    setattr(self.config, section_name, section_data)
    
    def _calculate_config_hash(self) -> str:
        """Calculate hash of current configuration"""
        config_dict = self._to_dict()
        config_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(config_str.encode('utf-8')).hexdigest()
    
    def has_changed(self) -> bool:
        """Check if config has changed since load"""
        if not self.config._config_hash:
            return True
        
        current_hash = self._calculate_config_hash()
        return current_hash != self.config._config_hash

# Singleton instance
_config_manager: Optional[ConfigManager] = None

def get_config_manager(config_path: Optional[Path] = None) -> ConfigManager:
    """Get or create configuration manager singleton"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
