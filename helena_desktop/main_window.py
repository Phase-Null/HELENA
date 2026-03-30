"""
HELENA Desktop — Main Application Window
 
Single-panel layout:
  Left:  ChatInterface (conversation)
  Right: RightPanel (orb + console + files + modes)
"""
import sys
import time
import threading
from pathlib import Path
 
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QLabel,
    QMessageBox, QSystemTrayIcon, QMenu, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon, QAction, QColor, QPalette
 
sys.path.insert(0, str(Path(__file__).parent.parent))
from helena_core.utils.logging import init_logging, get_logger
 
log_dir = Path.home() / ".helena" / "logs"
init_logging(log_dir)
 
from helena_core.utils.config_manager import get_config_manager
from helena_core.kernel import HELENAKernel
from helena_core.runtime import HELENARuntime
from helena_core.memory import HELENAMemory
from helena_training import AutonomousTrainer
 
from .chat_interface import ChatInterface
from .right_panel import RightPanel
 
logger = get_logger()
 
GLOBAL_STYLE = """
QMainWindow, QWidget {
    background: #080808;
    color: #cccccc;
}
QToolTip {
    background: #0f0f0f;
    color: #c9a84c;
    border: 1px solid rgba(201,168,76,0.3);
    font-family: 'Courier New', monospace;
    font-size: 9px;
}
"""
 
 
class TitleBar(QWidget):
    """Custom minimal title bar."""
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(
            "background:#0e0e0e;border-bottom:1px solid #1a1a1a;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
 
        # Traffic light dots (decorative)
        for color in ("#3a2a2a", "#2a2a1a", "#1a2a1a"):
            dot = QFrame()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background:{color};border-radius:4px;")
            layout.addWidget(dot)
 
        layout.addSpacing(12)
 
        title = QLabel("H E L E N A")
        title.setStyleSheet(
            "color:#c9a84c;font-family:'Courier New',monospace;"
            "font-size:11px;letter-spacing:3px;"
        )
        layout.addWidget(title)
        layout.addStretch()
 
        self._status = QLabel("ENGINEERING MODE")
        self._status.setStyleSheet(
            "color:#333;font-family:'Courier New',monospace;"
            "font-size:9px;letter-spacing:2px;"
        )
        layout.addWidget(self._status)
 
    def set_status(self, text: str) -> None:
        self._status.setText(text)
 
 
class MainWindow(QMainWindow):
    """Main HELENA application window."""
 
    def __init__(self):
        super().__init__()
 
        # Core systems
        self.config_manager = get_config_manager(
            Path.home() / ".helena" / "config.yaml"
        )
        self.memory = HELENAMemory(self.config_manager)
        self.kernel = HELENAKernel(
            "primary_operator",
            self.config_manager,
            memory_system=self.memory
        )
        self.runtime = HELENARuntime(self.config_manager)
 
        self.kernel.initialize()
        self.runtime.initialize()
 
        try:
            from helena_training import AutonomousTrainer
            self.trainer = AutonomousTrainer(self.kernel, self.memory, self.config_manager)
        except Exception:
            self.trainer = None
 
        self._build_ui()
        self._setup_window()
        self._setup_tray()
 
        logger.info("MainWindow", "HELENA desktop initialised")
 
    def _build_ui(self) -> None:
        self.setStyleSheet(GLOBAL_STYLE)
 
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
 
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
 
        # Title bar
        self._title_bar = TitleBar()
        outer.addWidget(self._title_bar)
 
        # Main body
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
 
        # Chat (left, stretches)
        self._chat = ChatInterface(self.kernel)
        self._chat.response_received.connect(self._on_helena_response)
        body_layout.addWidget(self._chat, stretch=1)
 
        # Divider
        div = QFrame()
        div.setFixedWidth(1)
        div.setStyleSheet("background:#1a1a1a;")
        body_layout.addWidget(div)
 
        # Right panel (fixed width)
        self._right = RightPanel(kernel=self.kernel)
        self._right.mode_changed.connect(self._on_mode_changed)
        self._right.file_selected.connect(self._on_file_selected)
        body_layout.addWidget(self._right)
 
        outer.addWidget(body, stretch=1)
 
        # Log startup to console
        self._right.log("[OK] kernel initialised", "ok")
        self._right.log("[OK] memory online", "ok")
 
        llm_status = "helena-net" if self._detect_helena_net() else "ollama/mistral"
        self._right.log(f"[OK] llm: {llm_status}", "ok")
 
    def _setup_window(self) -> None:
        self.setWindowTitle("HELENA")
        self.resize(1100, 720)
        self.setMinimumSize(800, 560)
 
        # Dark palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#080808"))
        palette.setColor(QPalette.WindowText, QColor("#cccccc"))
        palette.setColor(QPalette.Base, QColor("#0f0f0f"))
        palette.setColor(QPalette.Text, QColor("#cccccc"))
        self.setPalette(palette)
 
    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        menu = QMenu()
        show_action = QAction("Show HELENA", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()
 
    # ── Event handlers ────────────────────────────────────────────
 
    def _on_helena_response(self, text: str) -> None:
        """Animate the orb and update params when HELENA responds."""
        self._right.speak(text)
 
        # Update personality param bars if available
        try:
            pe = self.kernel.personality_engine
            if hasattr(pe, 'profile'):
                p = pe.profile
                self._right.update_params(
                    p.verbosity,
                    p.technical_depth,
                    self.kernel.emotion_engine.get_state().get("mood", 0.5)
                    if hasattr(self.kernel, 'emotion_engine') else 0.5
                )
        except Exception:
            pass
 
    def _on_mode_changed(self, mode: str) -> None:
        """Change kernel operational mode."""
        from helena_core.kernel.modes import OperationalMode
        mode_map = {
            "ENGINEERING": OperationalMode.ENGINEERING,
            "DEFENSIVE": OperationalMode.DEFENSIVE,
            "TOOL": OperationalMode.TOOL,
            "BACKGROUND": OperationalMode.BACKGROUND,
        }
        if mode in mode_map:
            self.kernel.change_mode(mode_map[mode])
            self._title_bar.set_status(f"{mode} MODE")
            self._right.log(f"[--] mode changed: {mode}", "info")
 
    def _on_file_selected(self, path: str) -> None:
        """Handle a file being dropped or selected."""
        self._right.log(f"[FILE] {path}", "info")
        # Route file content to chat engine as context
        try:
            content = open(path, 'r', encoding='utf-8', errors='replace').read()[:2000]
            self.kernel.submit_task(
                command="chat",
                parameters={"message": f"[File loaded: {path}]\n\n{content[:500]}..."},
                source="operator"
            )
        except Exception as e:
            self._right.log(f"[ERR] could not read file: {e}", "error")
 
    # ── Helpers ───────────────────────────────────────────────────
 
    def _detect_helena_net(self) -> bool:
        try:
            from pathlib import Path
            model_path = Path(__file__).parent.parent / "helena_memory" / "helena_net" / "model.pt"
            return model_path.exists()
        except Exception:
            return False
 
    def _quit(self) -> None:
        try:
            self.memory.save()
            self.kernel.shutdown()
            self.runtime.shutdown()
        except Exception:
            pass
        QApplication.quit()
 
    def closeEvent(self, event) -> None:
        reply = QMessageBox.question(
            self, "Exit HELENA",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.memory.save()
                self.kernel.shutdown()
                self.runtime.shutdown()
            except Exception:
                pass
            event.accept()
        else:
            event.ignore()
 
 
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HELENA")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
 
 
if __name__ == "__main__":
    main()
 
