"""
HELENA Right Panel
 
Contains:
- Orb visualizer (voice pattern)
- System console output
- File drop zone with recent files
- Mode selector
- Parameter readouts
"""
import json
from pathlib import Path
 
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
 
from .orb_widget import OrbWidget
 
 
RECENT_FILES_PATH = Path.home() / ".helena" / "recent_files.json"
MAX_RECENT = 6
 
 
class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "color:#c9a84c; font-family:'Courier New',monospace; "
            "font-size:9px; letter-spacing:3px; padding:0; margin:0;"
        )
 
 
class ModeButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self._update_style(False)
        self.toggled.connect(self._update_style)
 
    def _update_style(self, checked):
        if checked:
            self.setStyleSheet(
                "QPushButton{background:#0f0e0a;border:1px solid rgba(201,168,76,0.35);"
                "color:rgba(201,168,76,0.7);font-family:'Courier New',monospace;"
                "font-size:8px;letter-spacing:1px;padding:5px 4px;border-radius:3px;}"
            )
        else:
            self.setStyleSheet(
                "QPushButton{background:#0f0f0f;border:1px solid #1e1e1e;color:#444;"
                "font-family:'Courier New',monospace;font-size:8px;letter-spacing:1px;"
                "padding:5px 4px;border-radius:3px;}"
                "QPushButton:hover{border:1px solid #333;color:#666;}"
            )
 
 
class ParamBar(QWidget):
    def __init__(self, label, value=0.5, parent=None):
        super().__init__(parent)
        self._value = value
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
 
        lbl = QLabel(label)
        lbl.setStyleSheet(
            "color:#333;font-family:'Courier New',monospace;"
            "font-size:8px;letter-spacing:1px;"
        )
        lbl.setFixedWidth(80)
 
        self._bg = QFrame()
        self._bg.setFixedSize(80, 3)
        self._bg.setStyleSheet("background:#1a1a1a;border-radius:2px;")
 
        self._fill = QFrame(self._bg)
        self._fill.setFixedHeight(3)
        self._fill.setStyleSheet("background:rgba(201,168,76,0.5);border-radius:2px;")
        self._fill.setFixedWidth(int(80 * value))
 
        layout.addWidget(lbl)
        layout.addWidget(self._bg)
        layout.addStretch()
 
    def set_value(self, value):
        self._value = max(0.0, min(1.0, value))
        self._fill.setFixedWidth(int(80 * self._value))
 
 
class FileDropZone(QWidget):
    file_dropped = Signal(str)
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._recent = self._load_recent()
        self._build_ui()
 
    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
 
        self._drop_frame = QFrame()
        self._drop_frame.setFixedHeight(44)
        self._drop_frame.setCursor(Qt.PointingHandCursor)
        self._set_drop_style(False)
 
        inner = QHBoxLayout(self._drop_frame)
        inner.setContentsMargins(8, 4, 8, 4)
        plus = QLabel("+")
        plus.setStyleSheet("color:#2a2a2a;font-size:14px;border:none;")
        lbl = QLabel("DROP FILES OR CLICK TO BROWSE")
        lbl.setStyleSheet(
            "color:#2a2a2a;font-family:'Courier New',monospace;"
            "font-size:8px;letter-spacing:1px;border:none;"
        )
        inner.addWidget(plus)
        inner.addWidget(lbl)
        inner.addStretch()
        self._layout.addWidget(self._drop_frame)
 
        self._rebuild_recent()
 
    def _set_drop_style(self, active):
        if active:
            self._drop_frame.setStyleSheet(
                "QFrame{border:1px dashed rgba(201,168,76,0.6);"
                "border-radius:4px;background:#0f0e0a;}"
            )
        else:
            self._drop_frame.setStyleSheet(
                "QFrame{border:1px dashed #2a2a2a;border-radius:4px;background:#050505;}"
                "QFrame:hover{border:1px dashed rgba(201,168,76,0.3);}"
            )
 
    def _rebuild_recent(self):
        for i in reversed(range(self._layout.count())):
            item = self._layout.itemAt(i)
            if item and item.widget() and item.widget() != self._drop_frame:
                item.widget().deleteLater()
                self._layout.removeItem(item)
 
        for path in self._recent[:MAX_RECENT]:
            name = Path(path).name
            btn = QPushButton(f"  {name}")
            btn.setStyleSheet(
                "QPushButton{background:none;border:none;border-left:1px solid #1a1a1a;"
                "color:#333;font-family:'Courier New',monospace;font-size:8px;"
                "letter-spacing:1px;padding:3px 6px;text-align:left;border-radius:0;}"
                "QPushButton:hover{color:rgba(201,168,76,0.5);"
                "border-left:1px solid rgba(201,168,76,0.3);}"
            )
            btn.clicked.connect(lambda _, p=path: self.file_dropped.emit(p))
            self._layout.addWidget(btn)
 
    def mousePressEvent(self, event):
        if self._drop_frame.geometry().contains(event.pos()):
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
            if path:
                self._add(path)
                self.file_dropped.emit(path)
 
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drop_style(True)
 
    def dragLeaveEvent(self, event):
        self._set_drop_style(False)
 
    def dropEvent(self, event):
        self._set_drop_style(False)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._add(path)
                self.file_dropped.emit(path)
 
    def _add(self, path):
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        self._recent = self._recent[:MAX_RECENT]
        self._save_recent()
        self._rebuild_recent()
 
    def _load_recent(self):
        try:
            if RECENT_FILES_PATH.exists():
                with open(RECENT_FILES_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
        return []
 
    def _save_recent(self):
        try:
            RECENT_FILES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(RECENT_FILES_PATH, 'w') as f:
                json.dump(self._recent, f)
        except Exception:
            pass
 
 
class RightPanel(QWidget):
    mode_changed = Signal(str)
    file_selected = Signal(str)
 
    def __init__(self, kernel=None, parent=None):
        super().__init__(parent)
        self.kernel = kernel
        self.setFixedWidth(260)
        self.setStyleSheet("background:#080808;")
        self._build_ui()
        self._start_console_timer()
 
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
 
        def section(widget):
            widget.setStyleSheet(
                widget.styleSheet() + "border-bottom:1px solid #1a1a1a;"
            )
            layout.addWidget(widget)
 
        # Orb
        orb_w = QWidget()
        orb_l = QVBoxLayout(orb_w)
        orb_l.setContentsMargins(16, 12, 16, 12)
        orb_l.setSpacing(4)
        orb_l.addWidget(SectionLabel("VOICE PATTERN"))
        self.orb = OrbWidget()
        orb_l.addWidget(self.orb, alignment=Qt.AlignCenter)
        section(orb_w)
 
        # Console
        con_w = QWidget()
        con_l = QVBoxLayout(con_w)
        con_l.setContentsMargins(16, 10, 16, 10)
        con_l.setSpacing(6)
        con_l.addWidget(SectionLabel("SYSTEM CONSOLE"))
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFixedHeight(80)
        self._console.setStyleSheet(
            "QTextEdit{background:#050505;border:1px solid #1a1a1a;color:#444;"
            "font-family:'Courier New',monospace;font-size:9px;"
            "padding:6px;border-radius:4px;}"
        )
        self._console.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        con_l.addWidget(self._console)
        section(con_w)
 
        # File drop
        file_w = QWidget()
        file_l = QVBoxLayout(file_w)
        file_l.setContentsMargins(16, 10, 16, 10)
        file_l.setSpacing(6)
        file_l.addWidget(SectionLabel("FILE ACCESS"))
        self._file_drop = FileDropZone()
        self._file_drop.file_dropped.connect(self.file_selected.emit)
        file_l.addWidget(self._file_drop)
        section(file_w)
 
        # Mode
        mode_w = QWidget()
        mode_l = QVBoxLayout(mode_w)
        mode_l.setContentsMargins(16, 10, 16, 10)
        mode_l.setSpacing(6)
        mode_l.addWidget(SectionLabel("MODE"))
 
        btn_row = QWidget()
        btn_grid = QHBoxLayout(btn_row)
        btn_grid.setContentsMargins(0, 0, 0, 0)
        btn_grid.setSpacing(4)
 
        self._mode_btns = {}
        for mode in ["ENGINEERING", "DEFENSIVE", "TOOL", "BACKGROUND"]:
            btn = ModeButton(mode)
            btn.setFixedHeight(26)
            if mode == "ENGINEERING":
                btn.setChecked(True)
            btn.toggled.connect(lambda checked, m=mode: self._on_mode(m, checked))
            self._mode_btns[mode] = btn
            btn_grid.addWidget(btn)
 
        mode_l.addWidget(btn_row)
        section(mode_w)
 
        # Params
        param_w = QWidget()
        param_l = QVBoxLayout(param_w)
        param_l.setContentsMargins(16, 10, 16, 12)
        param_l.setSpacing(5)
        param_l.addWidget(SectionLabel("PARAMETERS"))
 
        self._p_verbosity = ParamBar("VERBOSITY", 0.4)
        self._p_depth = ParamBar("TECH DEPTH", 0.8)
        self._p_emotion = ParamBar("EMOTION", 0.65)
        param_l.addWidget(self._p_verbosity)
        param_l.addWidget(self._p_depth)
        param_l.addWidget(self._p_emotion)
        layout.addWidget(param_w)
        layout.addStretch()
 
    def _start_console_timer(self):
        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._poll_kernel)
        self._ctimer.start(3000)
        self.log("[OK] interface initialised", "ok")
 
    def log(self, message, level="info"):
        colors = {"ok": "#3a7a4a", "info": "rgba(201,168,76,0.6)",
                  "warn": "#7a5a2a", "error": "#7a2a2a"}
        color = colors.get(level, "#444")
        self._console.append(
            f'<span style="color:{color};font-family:Courier New;font-size:9px;">'
            f'{message}</span>'
        )
        sb = self._console.verticalScrollBar()
        sb.setValue(sb.maximum())
 
    def _poll_kernel(self):
        if self.kernel:
            try:
                status = self.kernel.get_system_status()
                mode = status.get("mode", "?")
                tasks = status.get("metrics", {}).get("tasks_processed", 0)
                self.log(f"[--] mode:{mode} tasks:{tasks}", "info")
            except Exception:
                pass
 
    def _on_mode(self, mode, checked):
        if checked:
            for m, btn in self._mode_btns.items():
                if m != mode:
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            self.mode_changed.emit(mode)
 
    def speak(self, text):
        self.orb.speak(text)
 
    def stop_speaking(self):
        self.orb.stop_speaking()
 
    def update_params(self, verbosity, depth, emotion):
        self._p_verbosity.set_value(verbosity)
        self._p_depth.set_value(depth)
        self._p_emotion.set_value(emotion)
