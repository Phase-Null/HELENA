# helena_core/runtime/hardware.py
"""
Hardware abstraction layer for cross-platform compatibility
"""
import platform
import sys
import os
import ctypes
import subprocess
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
import time
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import GPUtil
    HAS_GPUINFO = True
except ImportError:
    HAS_GPUINFO = False

logger = logging.getLogger(__name__)

class ProcessorArchitecture(Enum):
    """Processor architecture types"""
    X86_64 = auto()
    ARM64 = auto()
    ARM32 = auto()
    UNKNOWN = auto()

class GPUPlatform(Enum):
    """GPU platform types"""
    NVIDIA = auto()
    AMD = auto()
    INTEL = auto()
    APPLE_METAL = auto()
    INTEGRATED = auto()
    UNKNOWN = auto()

@dataclass
class CPUInfo:
    """CPU information"""
    architecture: ProcessorArchitecture
    brand: str
    physical_cores: int
    logical_cores: int
    base_frequency_ghz: float
    max_frequency_ghz: float
    l1_cache_kb: int
    l2_cache_kb: int
    l3_cache_kb: int
    features: List[str] = field(default_factory=list)
    temperature_c: Optional[float] = None

@dataclass
class GPUInfo:
    """GPU information"""
    platform: GPUPlatform
    name: str
    memory_total_mb: int
    memory_used_mb: int = 0
    memory_free_mb: int = 0
    utilization: float = 0.0
    temperature_c: Optional[float] = None
    driver_version: Optional[str] = None
    cuda_cores: Optional[int] = None
    is_integrated: bool = False
    supports_cuda: bool = False
    supports_opencl: bool = False
    supports_metal: bool = False

@dataclass
class MemoryInfo:
    """Memory information"""
    total_mb: int
    available_mb: int
    used_mb: int
    swap_total_mb: int
    swap_used_mb: int
    memory_speed_mhz: Optional[int] = None
    memory_type: Optional[str] = None

@dataclass
class StorageInfo:
    """Storage information"""
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    fs_type: str
    is_ssd: Optional[bool] = None
    read_speed_mbps: Optional[float] = None
    write_speed_mbps: Optional[float] = None

@dataclass
class ThermalInfo:
    """Thermal information"""
    cpu_temp_c: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    system_temp_c: Optional[float] = None
    fan_speeds_rpm: Dict[str, int] = field(default_factory=dict)
    thermal_zones: Dict[str, float] = field(default_factory=dict)

@dataclass
class HardwareProfile:
    """Complete hardware profile"""
    system_name: str
    system_version: str
    cpu: CPUInfo
    gpus: List[GPUInfo]
    memory: MemoryInfo
    storage: List[StorageInfo]
    thermal: ThermalInfo
    network_interfaces: List[Dict[str, Any]]
    power_supply: Optional[Dict[str, Any]] = None
    display_info: Optional[Dict[str, Any]] = None
    detection_time: float = field(default_factory=time.time)

class HardwareDetector:
    """Cross-platform hardware detector"""
    
    def __init__(self):
        self.profile: Optional[HardwareProfile] = None
        self.cache_time: Optional[float] = None
        self.cache_duration = 300  # Cache for 5 minutes
        
        # Platform-specific modules
        self.platform = platform.system().lower()
        self._init_platform_specific()
    
    def _init_platform_specific(self):
        """Initialize platform-specific detection modules"""
        if self.platform == 'windows':
            self._init_windows()
        elif self.platform == 'darwin':
            self._init_macos()
        elif self.platform == 'linux':
            self._init_linux()
        else:
            logger.warning(f"Unsupported platform: {self.platform}")
    
    def _init_windows(self):
        """Initialize Windows-specific detection"""
        try:
            import wmi
            self.wmi = wmi.WMI()
        except ImportError:
            self.wmi = None
            logger.warning("WMI not available, limited hardware detection")
    
    def _init_macos(self):
        """Initialize macOS-specific detection"""
        # Check for ioreg and system_profiler
        self.has_ioreg = self._check_command('ioreg')
        self.has_system_profiler = self._check_command('system_profiler')
    
    def _init_linux(self):
        """Initialize Linux-specific detection"""
        # Check for common Linux utilities
        self.has_lscpu = self._check_command('lscpu')
        self.has_lshw = self._check_command('lshw')
        self.has_sensors = self._check_command('sensors')
        self.has_nvidia_smi = self._check_command('nvidia-smi')
    
    def detect(self, force_refresh: bool = False) -> HardwareProfile:
        """Detect hardware and return profile"""
        if not force_refresh and self.profile and self.cache_time:
            if time.time() - self.cache_time < self.cache_duration:
                return self.profile
        
        try:
            logger.info("HardwareDetector", "Starting hardware detection")
            
            # Detect CPU
            cpu_info = self._detect_cpu()
            
            # Detect GPUs
            gpu_info = self._detect_gpus()
            
            # Detect Memory
            memory_info = self._detect_memory()
            
            # Detect Storage
            storage_info = self._detect_storage()
            
            # Detect Thermal
            thermal_info = self._detect_thermal()
            
            # Detect Network
            network_info = self._detect_network()
            
            # Detect Power
            power_info = self._detect_power()
            
            # Detect Displays
            display_info = self._detect_displays()
            
            # Create profile
            self.profile = HardwareProfile(
                system_name=platform.system(),
                system_version=platform.version(),
                cpu=cpu_info,
                gpus=gpu_info,
                memory=memory_info,
                storage=storage_info,
                thermal=thermal_info,
                network_interfaces=network_info,
                power_supply=power_info,
                display_info=display_info
            )
            
            self.cache_time = time.time()
            logger.info("HardwareDetector", "Hardware detection completed")
            
            return self.profile
            
        except Exception as e:
            logger.error("HardwareDetector", f"Hardware detection failed: {e}")
            # Return minimal profile
            return self._create_minimal_profile()
    
    def _detect_cpu(self) -> CPUInfo:
        """Detect CPU information"""
        try:
            if self.platform == 'windows':
                return self._detect_cpu_windows()
            elif self.platform == 'darwin':
                return self._detect_cpu_macos()
            elif self.platform == 'linux':
                return self._detect_cpu_linux()
            else:
                return self._detect_cpu_generic()
        except Exception as e:
            logger.error("HardwareDetector", f"CPU detection failed: {e}")
            return self._detect_cpu_generic()
    
    def _detect_cpu_windows(self) -> CPUInfo:
        """Detect CPU on Windows"""
        import cpuinfo
        
        info = cpuinfo.get_cpu_info()
        
        # Determine architecture
        arch_str = info.get('arch_string_raw', '').lower()
        if 'x86_64' in arch_str or 'amd64' in arch_str:
            arch = ProcessorArchitecture.X86_64
        elif 'arm64' in arch_str:
            arch = ProcessorArchitecture.ARM64
        elif 'arm' in arch_str:
            arch = ProcessorArchitecture.ARM32
        else:
            arch = ProcessorArchitecture.UNKNOWN
        
        # Get frequencies
        freq = info.get('hz_actual_friendly', '0 GHz')
        base_freq = float(freq.split()[0]) if ' ' in freq else 0
        
        max_freq = base_freq
        if 'hz_advertised_friendly' in info:
            max_freq_str = info['hz_advertised_friendly']
            max_freq = float(max_freq_str.split()[0]) if ' ' in max_freq_str else base_freq
        
        # Get cache sizes
        l1_cache = info.get('l1_data_cache_size', 0) or 0
        l2_cache = info.get('l2_cache_size', 0) or 0
        l3_cache = info.get('l3_cache_size', 0) or 0
        
        # Get features
        features = info.get('flags', [])
        
        # Get temperatures (requires WMI)
        temp = None
        if self.wmi:
            try:
                temperatures = self.wmi.Win32_PerfFormattedData_Counters_ThermalZoneInformation()
                if temperatures:
                    temp = float(temperatures[0].Temperature)
            except Exception:
                pass
        
        return CPUInfo(
            architecture=arch,
            brand=info.get('brand_raw', 'Unknown CPU'),
            physical_cores=psutil.cpu_count(logical=False) if HAS_PSUTIL else info.get('count', 1),
            logical_cores=psutil.cpu_count(logical=True) if HAS_PSUTIL else info.get('count', 1),
            base_frequency_ghz=base_freq,
            max_frequency_ghz=max_freq,
            l1_cache_kb=l1_cache // 1024 if l1_cache else 0,
            l2_cache_kb=l2_cache // 1024 if l2_cache else 0,
            l3_cache_kb=l3_cache // 1024 if l3_cache else 0,
            features=features,
            temperature_c=temp
        )
    
    def _detect_cpu_macos(self) -> CPUInfo:
        """Detect CPU on macOS"""
        import cpuinfo
        
        info = cpuinfo.get_cpu_info()
        
        # Determine architecture
        arch_str = platform.machine().lower()
        if arch_str == 'x86_64':
            arch = ProcessorArchitecture.X86_64
        elif arch_str == 'arm64':
            arch = ProcessorArchitecture.ARM64
        else:
            arch = ProcessorArchitecture.UNKNOWN
        
        # Get frequencies using system_profiler
        base_freq = 0.0
        max_freq = 0.0
        
        if self.has_system_profiler:
            try:
                cmd = ['system_profiler', 'SPHardwareDataType']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                for line in result.stdout.split('\n'):
                    if 'Processor Speed' in line:
                        speed_str = line.split(':')[-1].strip()
                        if 'GHz' in speed_str:
                            freq = float(speed_str.replace('GHz', '').strip())
                            base_freq = max_freq = freq
                            break
            except Exception:
                pass
        
        # Get cache info
        l1_cache = info.get('l1_data_cache_size', 0) or 0
        l2_cache = info.get('l2_cache_size', 0) or 0
        l3_cache = info.get('l3_cache_size', 0) or 0
        
        # Get temperatures (macOS specific)
        temp = None
        if self.has_ioreg:
            try:
                cmd = ['ioreg', '-c', 'AppleARMPlatform', '-r', '-d', '1']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                for line in result.stdout.split('\n'):
                    if 'temperature' in line.lower():
                        parts = line.split('=')
                        if len(parts) > 1:
                            temp_str = parts[1].strip()
                            if temp_str.endswith(';'):
                                temp_str = temp_str[:-1]
                            temp = float(temp_str) / 1000.0  # Convert to Celsius
                            break
            except Exception:
                pass
        
        return CPUInfo(
            architecture=arch,
            brand=info.get('brand_raw', 'Apple Silicon' if arch == ProcessorArchitecture.ARM64 else 'Unknown'),
            physical_cores=psutil.cpu_count(logical=False) if HAS_PSUTIL else info.get('count', 1),
            logical_cores=psutil.cpu_count(logical=True) if HAS_PSUTIL else info.get('count', 1),
            base_frequency_ghz=base_freq,
            max_frequency_ghz=max_freq,
            l1_cache_kb=l1_cache // 1024 if l1_cache else 0,
            l2_cache_kb=l2_cache // 1024 if l2_cache else 0,
            l3_cache_kb=l3_cache // 1024 if l3_cache else 0,
            features=info.get('flags', []),
            temperature_c=temp
        )
    
    def _detect_cpu_linux(self) -> CPUInfo:
        """Detect CPU on Linux"""
        import cpuinfo
        
        info = cpuinfo.get_cpu_info()
        
        # Determine architecture
        arch_str = platform.machine().lower()
        if 'x86_64' in arch_str or 'amd64' in arch_str:
            arch = ProcessorArchitecture.X86_64
        elif 'aarch64' in arch_str or 'arm64' in arch_str:
            arch = ProcessorArchitecture.ARM64
        elif 'arm' in arch_str:
            arch = ProcessorArchitecture.ARM32
        else:
            arch = ProcessorArchitecture.UNKNOWN
        
        # Get frequencies from /proc/cpuinfo or lscpu
        base_freq = 0.0
        max_freq = 0.0
        
        if self.has_lscpu:
            try:
                cmd = ['lscpu']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                for line in result.stdout.split('\n'):
                    if 'CPU max MHz' in line:
                        max_freq = float(line.split(':')[-1].strip()) / 1000.0
                    elif 'CPU min MHz' in line:
                        base_freq = float(line.split(':')[-1].strip()) / 1000.0
            except Exception:
                pass
        
        # Get cache info
        l1_cache = info.get('l1_data_cache_size', 0) or 0
        l2_cache = info.get('l2_cache_size', 0) or 0
        l3_cache = info.get('l3_cache_size', 0) or 0
        
        # Get temperature
        temp = None
        if self.has_sensors:
            try:
                cmd = ['sensors', '-u']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                for line in result.stdout.split('\n'):
                    if 'temp1_input' in line:
                        temp = float(line.split(':')[-1].strip())
                        break
            except Exception:
                # Try thermal zone
                thermal_zone = '/sys/class/thermal/thermal_zone0/temp'
                if os.path.exists(thermal_zone):
                    try:
                        with open(thermal_zone, 'r') as f:
                            temp = float(f.read().strip()) / 1000.0
                    except Exception:
                        pass
        
        return CPUInfo(
            architecture=arch,
            brand=info.get('brand_raw', 'Unknown CPU'),
            physical_cores=psutil.cpu_count(logical=False) if HAS_PSUTIL else info.get('count', 1),
            logical_cores=psutil.cpu_count(logical=True) if HAS_PSUTIL else info.get('count', 1),
            base_frequency_ghz=base_freq,
            max_frequency_ghz=max_freq,
            l1_cache_kb=l1_cache // 1024 if l1_cache else 0,
            l2_cache_kb=l2_cache // 1024 if l2_cache else 0,
            l3_cache_kb=l3_cache // 1024 if l3_cache else 0,
            features=info.get('flags', []),
            temperature_c=temp
        )
    
    def _detect_cpu_generic(self) -> CPUInfo:
        """Generic CPU detection as fallback"""
        import cpuinfo
        
        info = cpuinfo.get_cpu_info()
        
        return CPUInfo(
            architecture=ProcessorArchitecture.UNKNOWN,
            brand=info.get('brand_raw', 'Unknown CPU'),
            physical_cores=psutil.cpu_count(logical=False) if HAS_PSUTIL else 1,
            logical_cores=psutil.cpu_count(logical=True) if HAS_PSUTIL else 1,
            base_frequency_ghz=0.0,
            max_frequency_ghz=0.0,
            l1_cache_kb=0,
            l2_cache_kb=0,
            l3_cache_kb=0,
            features=[]
        )
    
    def _detect_gpus(self) -> List[GPUInfo]:
        """Detect GPU information"""
        gpus = []
        
        # Try GPUtil first (NVIDIA)
        if HAS_GPUINFO:
            try:
                gputil_gpus = GPUtil.getGPUs()
                for gpu in gputil_gpus:
                    platform_type = GPUPlatform.NVIDIA
                    if 'amd' in gpu.name.lower():
                        platform_type = GPUPlatform.AMD
                    elif 'intel' in gpu.name.lower():
                        platform_type = GPUPlatform.INTEL
                    
                    gpus.append(GPUInfo(
                        platform=platform_type,
                        name=gpu.name,
                        memory_total_mb=int(gpu.memoryTotal),
                        memory_used_mb=int(gpu.memoryUsed),
                        memory_free_mb=int(gpu.memoryFree),
                        utilization=gpu.load * 100,
                        temperature_c=gpu.temperature,
                        driver_version=None,
                        supports_cuda=platform_type == GPUPlatform.NVIDIA,
                        supports_opencl=True,
                        is_integrated='integrated' in gpu.name.lower()
                    ))
                return gpus
            except Exception:
                pass
        
        # Platform-specific detection
        if self.platform == 'windows':
            return self._detect_gpus_windows()
        elif self.platform == 'darwin':
            return self._detect_gpus_macos()
        elif self.platform == 'linux':
            return self._detect_gpus_linux()
        
        return gpus
    
    def _detect_gpus_windows(self) -> List[GPUInfo]:
        """Detect GPUs on Windows"""
        gpus = []
        
        if self.wmi:
            try:
                # Get display adapters
                adapters = self.wmi.Win32_VideoController()
                
                for adapter in adapters:
                    name = adapter.Name or 'Unknown GPU'
                    
                    # Determine platform
                    platform_type = GPUPlatform.UNKNOWN
                    if 'nvidia' in name.lower():
                        platform_type = GPUPlatform.NVIDIA
                    elif 'amd' in name.lower() or 'radeon' in name.lower():
                        platform_type = GPUPlatform.AMD
                    elif 'intel' in name.lower():
                        platform_type = GPUPlatform.INTEL
                    
                    # Get memory (in bytes, convert to MB)
                    adapter_ram = getattr(adapter, 'AdapterRAM', 0)
                    memory_mb = adapter_ram // (1024 * 1024) if adapter_ram else 0
                    
                    gpus.append(GPUInfo(
                        platform=platform_type,
                        name=name,
                        memory_total_mb=memory_mb,
                        is_integrated='integrated' in name.lower(),
                        supports_cuda=platform_type == GPUPlatform.NVIDIA
                    ))
            except Exception as e:
                logger.error("HardwareDetector", f"Windows GPU detection failed: {e}")
        
        return gpus
    
    def _detect_gpus_macos(self) -> List[GPUInfo]:
        """Detect GPUs on macOS"""
        gpus = []
        
        if self.has_system_profiler:
            try:
                cmd = ['system_profiler', 'SPDisplaysDataType']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                
                current_gpu = None
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    
                    if 'Chipset Model:' in line:
                        if current_gpu:
                            gpus.append(current_gpu)
                        
                        name = line.split(':', 1)[-1].strip()
                        platform_type = GPUPlatform.APPLE_METAL
                        if 'radeon' in name.lower():
                            platform_type = GPUPlatform.AMD
                        elif 'intel' in name.lower():
                            platform_type = GPUPlatform.INTEL
                        
                        current_gpu = GPUInfo(
                            platform=platform_type,
                            name=name,
                            memory_total_mb=0,
                            is_integrated='integrated' in name.lower(),
                            supports_metal=True
                        )
                    
                    elif current_gpu and 'VRAM' in line:
                        # Parse VRAM like "VRAM (Total): 8 GB"
                        if 'GB' in line:
                            vram_gb = float(line.split(':')[-1].strip().split()[0])
                            current_gpu.memory_total_mb = int(vram_gb * 1024)
            except Exception as e:
                logger.error("HardwareDetector", f"macOS GPU detection failed: {e}")
        
        return gpus
    
    def _detect_gpus_linux(self) -> List[GPUInfo]:
        """Detect GPUs on Linux"""
        gpus = []
        
        # Try lspci
        try:
            cmd = ['lspci', '-nn']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            for line in result.stdout.split('\n'):
                if 'VGA' in line or '3D' in line or 'Display' in line:
                    name = line.split(':')[-1].strip()
                    
                    platform_type = GPUPlatform.UNKNOWN
                    if 'nvidia' in name.lower():
                        platform_type = GPUPlatform.NVIDIA
                    elif 'amd' in name.lower() or 'radeon' in name.lower():
                        platform_type = GPUPlatform.AMD
                    elif 'intel' in name.lower():
                        platform_type = GPUPlatform.INTEL
                    
                    # Check if integrated
                    is_integrated = 'integrated' in name.lower() or platform_type == GPUPlatform.INTEL
                    
                    gpus.append(GPUInfo(
                        platform=platform_type,
                        name=name,
                        memory_total_mb=0,  # Would need additional detection
                        is_integrated=is_integrated,
                        supports_cuda=platform_type == GPUPlatform.NVIDIA
                    ))
        except Exception as e:
            logger.error("HardwareDetector", f"Linux GPU detection failed: {e}")
        
        return gpus
    
    def _detect_memory(self) -> MemoryInfo:
        """Detect memory information"""
        if not HAS_PSUTIL:
            return MemoryInfo(
                total_mb=0,
                available_mb=0,
                used_mb=0,
                swap_total_mb=0,
                swap_used_mb=0
            )
        
        try:
            virt = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return MemoryInfo(
                total_mb=virt.total // (1024 * 1024),
                available_mb=virt.available // (1024 * 1024),
                used_mb=virt.used // (1024 * 1024),
                swap_total_mb=swap.total // (1024 * 1024),
                swap_used_mb=swap.used // (1024 * 1024)
            )
        except Exception as e:
            logger.error("HardwareDetector", f"Memory detection failed: {e}")
            return MemoryInfo(0, 0, 0, 0, 0)
    
    def _detect_storage(self) -> List[StorageInfo]:
        """Detect storage devices"""
        if not HAS_PSUTIL:
            return []
        
        try:
            storage_devices = []
            
            # Get disk partitions
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    
                    # Check if SSD (platform specific)
                    is_ssd = None
                    if self.platform == 'windows':
                        is_ssd = self._is_ssd_windows(partition.device)
                    elif self.platform in ['linux', 'darwin']:
                        is_ssd = self._is_ssd_unix(partition.device)
                    
                    storage_devices.append(StorageInfo(
                        path=partition.mountpoint,
                        total_gb=usage.total / (1024**3),
                        used_gb=usage.used / (1024**3),
                        free_gb=usage.free / (1024**3),
                        fs_type=partition.fstype,
                        is_ssd=is_ssd
                    ))
                except Exception:
                    continue
            
            return storage_devices
            
        except Exception as e:
            logger.error("HardwareDetector", f"Storage detection failed: {e}")
            return []
    
    def _is_ssd_windows(self, device_path: str) -> Optional[bool]:
        """Check if Windows drive is SSD"""
        try:
            import win32api
            import win32file
            
            # Get physical drive from device path
            drive_letter = device_path[0] + ':'
            
            # Query drive attributes
            hdevice = win32file.CreateFile(
                f"\\\\.\\{drive_letter}",
                0, win32file.FILE_SHARE_READ, None,
                win32file.OPEN_EXISTING, 0, None
            )
            
            try:
                # Query storage property
                # This is simplified - actual implementation would use Storage API
                return None
            finally:
                win32file.CloseHandle(hdevice)
        except Exception:
            return None
    
    def _is_ssd_unix(self, device_path: str) -> Optional[bool]:
        """Check if Unix drive is SSD"""
        try:
            # Try using rotational attribute on Linux
            if self.platform == 'linux':
                device_name = device_path.split('/')[-1]
                rotational_path = f"/sys/block/{device_name}/queue/rotational"
                
                if os.path.exists(rotational_path):
                    with open(rotational_path, 'r') as f:
                        rotational = f.read().strip()
                        return rotational == '0'
            
            return None
        except Exception:
            return None
    
    def _detect_thermal(self) -> ThermalInfo:
        """Detect thermal information"""
        thermal = ThermalInfo()
        
        # CPU temperature already detected in CPUInfo
        if self.profile and self.profile.cpu.temperature_c:
            thermal.cpu_temp_c = self.profile.cpu.temperature_c
        
        # GPU temperatures
        if self.profile and self.profile.gpus:
            for gpu in self.profile.gpus:
                if gpu.temperature_c:
                    thermal.gpu_temp_c = gpu.temperature_c
                    break
        
        # Try additional platform-specific thermal detection
        if self.platform == 'linux' and self.has_sensors:
            try:
                cmd = ['sensors', '-u']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                for line in result.stdout.split('\n'):
                    if '_input' in line and 'temp' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            sensor_name = parts[0].strip()
                            temp = float(parts[1].strip())
                            thermal.thermal_zones[sensor_name] = temp
            except Exception:
                pass
        
        return thermal
    
    def _detect_network(self) -> List[Dict[str, Any]]:
        """Detect network interfaces"""
        if not HAS_PSUTIL:
            return []
        
        try:
            interfaces = []
            net_io = psutil.net_io_counters(pernic=True)
            net_addrs = psutil.net_if_addrs()
            net_stats = psutil.net_if_stats()
            
            for interface_name in net_io.keys():
                if interface_name in net_addrs and interface_name in net_stats:
                    stats = net_stats[interface_name]
                    
                    interfaces.append({
                        'name': interface_name,
                        'is_up': stats.isup,
                        'duplex': stats.duplex,
                        'speed_mbps': stats.speed,
                        'mtu': stats.mtu,
                        'addresses': [
                            {
                                'family': str(addr.family),
                                'address': addr.address,
                                'netmask': addr.netmask if hasattr(addr, 'netmask') else None,
                                'broadcast': addr.broadcast if hasattr(addr, 'broadcast') else None
                            }
                            for addr in net_addrs[interface_name]
                        ]
                    })
            
            return interfaces
            
        except Exception as e:
            logger.error("HardwareDetector", f"Network detection failed: {e}")
            return []
    
    def _detect_power(self) -> Optional[Dict[str, Any]]:
        """Detect power supply information"""
        if not HAS_PSUTIL:
            return None
        
        try:
            battery = psutil.sensors_battery()
            if battery:
                return {
                    'has_battery': True,
                    'plugged_in': battery.power_plugged,
                    'percent': battery.percent,
                    'secs_left': battery.secsleft if hasattr(battery, 'secsleft') else None
                }
        except Exception:
            pass
        
        return None
    
    def _detect_displays(self) -> Optional[Dict[str, Any]]:
        """Detect display information"""
        # Platform-specific display detection
        if self.platform == 'windows':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                
                displays = []
                for i in range(user32.GetSystemMetrics(ctypes.c_int(80))):  # SM_CMONITORS
                    displays.append({
                        'width': user32.GetSystemMetrics(ctypes.c_int(0)),  # SM_CXSCREEN
                        'height': user32.GetSystemMetrics(ctypes.c_int(1)),  # SM_CYSCREEN
                        'dpi': user32.GetDpiForSystem()
                    })
                
                return {'count': len(displays), 'displays': displays}
            except Exception:
                pass
        
        return None
    
    def _create_minimal_profile(self) -> HardwareProfile:
        """Create minimal hardware profile as fallback"""
        return HardwareProfile(
            system_name=platform.system(),
            system_version=platform.version(),
            cpu=self._detect_cpu_generic(),
            gpus=[],
            memory=self._detect_memory(),
            storage=[],
            thermal=ThermalInfo(),
            network_interfaces=[],
            power_supply=None,
            display_info=None
        )
    
    def _check_command(self, command: str) -> bool:
        """Check if a command is available"""
        try:
            subprocess.run(['which', command], capture_output=True, timeout=2)
            return True
        except Exception:
            return False
    
    def get_hardware_summary(self) -> Dict[str, Any]:
        """Get summarized hardware information"""
        if not self.profile:
            self.detect()
        
        summary = {
            'system': {
                'platform': self.profile.system_name,
                'version': self.profile.system_version
            },
            'cpu': {
                'brand': self.profile.cpu.brand,
                'cores': self.profile.cpu.physical_cores,
                'threads': self.profile.cpu.logical_cores,
                'architecture': self.profile.cpu.architecture.name,
                'max_frequency_ghz': self.profile.cpu.max_frequency_ghz
            },
            'memory': {
                'total_gb': self.profile.memory.total_mb / 1024,
                'available_gb': self.profile.memory.available_mb / 1024
            },
            'gpu_count': len(self.profile.gpus),
            'gpus': [
                {
                    'name': gpu.name,
                    'memory_gb': gpu.memory_total_mb / 1024,
                    'platform': gpu.platform.name,
                    'supports_cuda': gpu.supports_cuda
                }
                for gpu in self.profile.gpus
            ],
            'storage': [
                {
                    'path': storage.path,
                    'total_gb': storage.total_gb,
                    'free_gb': storage.free_gb,
                    'is_ssd': storage.is_ssd
                }
                for storage in self.profile.storage
            ],
            'detection_time': self.profile.detection_time
        }
        
        return summary

# Global hardware detector instance
_hardware_detector: Optional[HardwareDetector] = None

def get_hardware_detector() -> HardwareDetector:
    """Get global hardware detector instance"""
    global _hardware_detector
    if _hardware_detector is None:
        _hardware_detector = HardwareDetector()
    return _hardware_detector
