"""
HELENA Desktop - Main Application Window
"""
import sys
import time
import threading
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QMessageBox, QSystemTrayIcon, QMenu
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon, QAction

# Initialize logging FIRST – before any core imports that need logging
sys.path.insert(0, str(Path(__file__).parent.parent))
from helena_core.utils.logging import init_logging, get_logger

# Set up logging directory (created by setup.py)
log_dir = Path.home() / ".helena" / "logs"
init_logging(log_dir)   # This initializes the global logger

# Now it's safe to import core components that use get_logger()
from helena_core.utils.config_manager import get_config_manager
from helena_core.kernel import HELENAKernel
from helena_core.runtime import HELENARuntime
from helena_core.memory import HELENAMemory
from helena_training import AutonomousTrainer

# Import UI tabs
from .chat_interface import ChatInterface
from .console_interface import ConsoleInterface
from .dashboard import Dashboard
from .controls import ControlsPanel

logger = get_logger()

class MainWindow(QMainWindow):
    """Main HELENA application window"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize HELENA core systems
        self.config_manager = get_config_manager(Path.home() / ".helena" / "config.yaml")
        self.memory = HELENAMemory(self.config_manager)
        self.kernel = HELENAKernel("primary_operator", self.config_manager, memory_system=self.memory)
        self.runtime = HELENARuntime(self.config_manager)
        
        # Initialize core systems
        self.kernel.initialize()
        self.runtime.initialize()
        # memory already initialized in its __init__
        
        from helena_training import AutonomousTrainer

        # ... after creating kernel, runtime, memory
        trainer = AutonomousTrainer(self.kernel, self.runtime, self.memory, self.config_manager)
        self.kernel.training = trainer  # inject into kernel
        trainer.scheduler.start()  # start monitoring thread

        # Set up the UI
        self.setWindowTitle("HELENA AI Platform")
        self.setGeometry(100, 100, 1280, 800)
        
        # Create central tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create tabs
        self.chat_tab = ChatInterface(self.kernel)
        self.console_tab = ConsoleInterface(self.kernel, self.runtime)
        self.dashboard_tab = Dashboard(self.kernel, self.runtime, self.memory)
        self.controls_tab = ControlsPanel(self.kernel, self.runtime, self.config_manager, trainer=self.kernel.training)
        
        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.console_tab, "Console")
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.controls_tab, "Controls")
        
        # Create system tray
        self._create_system_tray()
        
        # Status bar
        self.statusBar().showMessage("HELENA Ready")
        
        # Update timer for status bar
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(2000)
        
        logger.info("MainWindow", "MainWindow initialized")
    
    def _create_system_tray(self):
        """Create system tray icon with menu"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        self.tray_icon = QSystemTrayIcon(self)
        # You can set an actual icon later: self.tray_icon.setIcon(QIcon("icon.png"))
        
        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    def _update_status(self):
        """Update status bar with system info"""
        try:
            status = self.kernel.get_system_status()
            mode = status.get('mode', 'UNKNOWN')
            tasks = status.get('metrics', {}).get('tasks_processed', 0)
            self.statusBar().showMessage(f"Mode: {mode} | Tasks: {tasks}")
        except:
            pass
    
    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self, "Exit HELENA",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Shutdown core systems
            self.kernel.shutdown()
            self.runtime.shutdown()
            event.accept()
        else:
            event.ignore()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HELENA")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":

    main()
