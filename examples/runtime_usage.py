# examples/runtime_usage.py
"""
Example usage of HELENA Runtime
"""
import time
from pathlib import Path

# Import runtime components
from helena_core.runtime import (
    HELENARuntime,
    PerformanceProfile
)
from helena_core.utils.config_manager import get_config_manager
from helena_core.utils.logging import init_logging

def main():
    """Example runtime usage"""
    
    # Initialize logging
    logger = init_logging(
        log_directory=Path("./logs"),
        max_log_size_mb=10,
        log_retention_days=7
    )
    
    # Get configuration
    config_manager = get_config_manager(Path("./config.yaml"))
    config_manager.initialize("example_operator")
    
    # Create runtime
    runtime = HELENARuntime(config_manager)
    
    # Initialize runtime
    if not runtime.initialize():
        print("Failed to initialize runtime")
        return
    
    print("Runtime initialized")
    
    # Get hardware information
    hardware_summary = runtime.hardware.get_hardware_summary()
    print(f"\nHardware Summary:")
    print(f"  CPU: {hardware_summary['cpu']['brand']}")
    print(f"  Cores: {hardware_summary['cpu']['cores']} physical, "
          f"{hardware_summary['cpu']['threads']} logical")
    print(f"  RAM: {hardware_summary['memory']['total_gb']:.1f} GB")
    print(f"  GPUs: {hardware_summary['gpu_count']}")
    
    # Get current profile
    profile = runtime.get_current_profile()
    print(f"\nCurrent Profile: {profile['name']}")
    print(f"  CPU Limit: {profile['limits']['cpu_percent']}%")
    print(f"  RAM Limit: {profile['limits']['ram_mb'] / 1024:.1f} GB")
    
    # Switch profiles
    print("\nSwitching to BACKGROUND profile...")
    runtime.switch_profile("BACKGROUND")
    
    time.sleep(2)  # Wait for profile to apply
    
    # Get system status
    status = runtime.get_system_status()
    print(f"\nSystem Status:")
    print(f"  CPU Usage: {status['resources']['cpu_percent']:.1f}%")
    print(f"  RAM Usage: {status['resources']['ram_mb'] / 1024:.1f} GB")
    print(f"  Profile: {status['profile']['name']}")
    
    # Create custom profile
    print("\nCreating custom profile...")
    custom_config = {
        'cpu_limit_percent': 35.0,
        'gpu_limit_percent': 20.0,
        'ram_limit_mb': 8192,
        'description': 'Custom optimized profile',
        'power_saving': True,
        'response_time_target_ms': 1500
    }
    
    runtime.create_custom_profile("MyProfile", custom_config)
    
    # Get available profiles
    profiles = runtime.profile_manager.get_available_profiles()
    print(f"\nAvailable Profiles:")
    for p in profiles:
        if p['type'] == 'standard':
            print(f"  {p['name']}: {p['description']}")
    
    # Monitor for a bit
    print("\nMonitoring system for 10 seconds...")
    for i in range(10):
        status = runtime.get_system_status()
        print(f"  [{i+1}/10] CPU: {status['resources']['cpu_percent']:.1f}%, "
              f"RAM: {status['resources']['ram_percent']:.1f}%")
        time.sleep(1)
    
    # Emergency throttle demo
    print("\nTesting emergency throttle...")
    result = runtime.emergency_throttle()
    print(f"  Emergency action: {result['message']}")
    
    time.sleep(2)
    
    # Return to normal
    print("\nReturning to NORMAL profile...")
    runtime.switch_profile("NORMAL")
    
    # Shutdown
    print("\nShutting down runtime...")
    runtime.shutdown(graceful=True)
    print("Runtime shutdown complete")

if __name__ == "__main__":
    main()
