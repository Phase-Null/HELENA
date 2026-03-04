# scripts/setup.py
"""
HELENA Initialization Script
"""
import sys
import os
import argparse
from pathlib import Path
import getpass
import hashlib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helena_core.utils.config_manager import get_config_manager
from helena_core.utils.logging import init_logging
from helena_core.security.encryption import EncryptionManager

def initialize_helena():
    """Interactive HELENA initialization"""
    print("""
    ╔══════════════════════════════════════════╗
    ║         HELENA AI Platform               ║
    ║          Initialization                  ║
    ╚══════════════════════════════════════════╝
    """)
    
    # Get operator ID
    operator_id = input("Enter operator ID (default: primary_operator): ").strip()
    if not operator_id:
        operator_id = "primary_operator"
    
    # Get installation directory
    default_dir = Path.home() / ".helena"
    install_dir = input(f"Installation directory (default: {default_dir}): ").strip()
    if not install_dir:
        install_dir = default_dir
    else:
        install_dir = Path(install_dir)
    
    # Create directories
    print("\nCreating directory structure...")
    directories = [
        install_dir,
        install_dir / "data",
        install_dir / "logs",
        install_dir / "cache",
        install_dir / "modules",
        install_dir / "models",
        install_dir / "temp",
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {directory}")
    
    # Initialize configuration
    print("\nInitializing configuration...")
    config_manager = get_config_manager(install_dir / "config.yaml")
    
    # Generate encryption key from operator password
    print("\nSecurity setup:")
    use_password = input("Use password for encryption? (y/n, default: y): ").strip().lower()
    
    encryption_key = None
    if use_password != 'n':
        password = getpass.getpass("Enter encryption password (leave empty for random): ")
        if password:
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Passwords do not match!")
                return False
            
            # Generate key from password
            encryption_manager = EncryptionManager()
            encryption_key, salt = encryption_manager.generate_master_key(password)
            
            # Save salt
            salt_file = install_dir / "security" / "salt.bin"
            salt_file.parent.mkdir(parents=True, exist_ok=True)
            with open(salt_file, 'wb') as f:
                f.write(salt)
            
            print("  ✓ Password-based encryption configured")
        else:
            # Generate random key
            encryption_key = os.urandom(32)
            print("  ✓ Random encryption key generated")
    
    # Initialize configuration
    success = config_manager.initialize(operator_id, encryption_key)
    if not success:
        print("Failed to initialize configuration!")
        return False
    
    print("  ✓ Configuration initialized")
    
    # Initialize logging
    print("\nInitializing logging system...")
    logger = init_logging(
        log_directory=install_dir / "logs",
        encryption_key=encryption_key,
        max_log_size_mb=config_manager.config.system.max_log_size_mb,
        log_retention_days=config_manager.config.system.log_retention_days
    )
    
    logger.info("setup", "HELENA initialization started")
    print("  ✓ Logging system initialized")
    
    # Download initial models (optional)
    print("\nModel setup:")
    download_models = input("Download initial ML models? (y/n, default: y): ").strip().lower()
    
    if download_models != 'n':
        print("Downloading models...")
        # This would be implemented based on available models
        print("  (Model download will be implemented in next phase)")
    
    # Create startup script
    print("\nCreating startup scripts...")
    create_startup_script(install_dir, operator_id)
    
    # Validate installation
    print("\nValidating installation...")
    validation_result = validate_installation(install_dir, config_manager)
    
    if validation_result["success"]:
        print("  ✓ Installation validated successfully")
        print("\n" + "="*50)
        print("HELENA initialization complete!")
        print("\nNext steps:")
        print(f"1. Start HELENA: cd {install_dir} && python start_helena.py")
        print("2. Configure modules and preferences in the UI")
        print("3. Begin training with: helena train --enable")
        print("\nSecurity note: Keep your encryption key/password secure!")
        print("="*50)
        
        logger.info("setup", "HELENA initialization completed successfully")
        return True
    else:
        print("  ✗ Installation validation failed:")
        for error in validation_result["errors"]:
            print(f"    - {error}")
        
        logger.error("setup", f"Initialization failed: {validation_result['errors']}")
        return False

def create_startup_script(install_dir: Path, operator_id: str):
    """Create startup script for HELENA"""
    script_content = f'''#!/usr/bin/env python3
"""
HELENA Startup Script
"""
import sys
import os

# Add HELENA to path
sys.path.insert(0, r"{install_dir.parent}")

# Import HELENA
from helena_desktop.main_window import main

if __name__ == "__main__":
    # Set environment variables
    os.environ["HELENA_HOME"] = r"{install_dir}"
    os.environ["HELENA_OPERATOR"] = "{operator_id}"
    
    # Start HELENA
    main()
'''
    
    script_path = install_dir / "start_helena.py"
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    # Make executable on Unix-like systems
    if os.name != 'nt':
        import stat
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
    
    print(f"  ✓ Startup script created: {script_path}")

def validate_installation(install_dir: Path, config_manager) -> dict:
    """Validate installation"""
    errors = []
    
    # Check directories
    required_dirs = ["data", "logs", "cache", "config"]
    for dir_name in required_dirs:
        if not (install_dir / dir_name).exists():
            errors.append(f"Directory missing: {dir_name}")
    
    # Check configuration
    config_errors = config_manager.validate()
    if config_errors:
        for section, section_errors in config_errors.items():
            for error in section_errors:
                errors.append(f"Config {section}: {error}")
    
    # Check Python dependencies
    try:
        import psutil
        import cryptography
        import yaml
    except ImportError as e:
        errors.append(f"Missing dependency: {e.name}")
    
    # Check write permissions
    test_file = install_dir / "test_write.tmp"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except Exception:
        errors.append(f"No write permission in {install_dir}")
    
    return {
        "success": len(errors) == 0,
        "errors": errors
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize HELENA AI Platform")
    parser.add_argument("--non-interactive", action="store_true", help="Non-interactive mode")
    parser.add_argument("--operator", help="Operator ID")
    parser.add_argument("--directory", help="Installation directory")
    
    args = parser.parse_args()
    
    if args.non_interactive:
        # Non-interactive mode for automated deployment
        print("Non-interactive mode not yet implemented")
        sys.exit(1)
    else:
        success = initialize_helena()
        sys.exit(0 if success else 1)
