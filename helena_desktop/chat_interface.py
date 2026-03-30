"""
HELENA Chat Interface — dark sci-fi styled chat panel.
"""
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from helena_core.kernel import TaskPriority
 
 
class ChatWorker(QThread):
    response_ready = Signal(str)
    error = Signal(str)
 
    def __init__(self, kernel, message):
        super().__init__()
        self.kernel = kernel
        self.message = message
 
    def run(self):
        try:
            task_id = self.kernel.submit_task(
                command="chat",
                parameters={"message": self.message},
                source="operator",
                priority=TaskPriority.NORMAL
            )
            if not task_id:
                self.error.emit("Task submission failed")
                return
            for _ in range(300):
                time.sleep(0.1)
                result = self.kernel.get_task_status(task_id)
                if result and result.get("status") == "completed":
                    task_result = result.get("result", {})
                    if isinstance(task_result, dict):
                        output = task_result.get("output", {})
                        if isinstance(output, dict) and output.get("summary"):
                            self.response_ready.emit(output["summary"])
                            return
                        if task_result.get("summary"):
                            self.response_ready.emit(task_result["summary"])
                            return
                        if isinstance(task_result.get("result"), str):
                            self.response_ready.emit(task_result["result"])
                            return
                        self.response_ready.emit(str(task_result))
                        return
                    self.response_ready.emit(str(task_result))
                    return
            self.error.emit("Response timeout")
        except Exception as e:
            self.error.emit(str(e))
 
 
class MessageBubble(QWidget):
    def __init__(self, text, role, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        is_user = role == "user"
 
        lbl = QLabel("PHASE-NULL" if is_user else "HELENA")
        lbl.setStyleSheet(
            f"color:{'#555' if is_user else 'rgba(201,168,76,0.5)'};"
            "font-family:'Courier New',monospace;font-size:9px;letter-spacing:2px;"
        )
        if is_user:
            lbl.setAlignment(Qt.AlignRight)
 
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setMaximumWidth(440)
        bubble.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
 
        if is_user:
            bubble.setStyleSheet(
                "background:#141414;border:1px solid #2a2a2a;color:#aaa;"
                "font-family:'Courier New',monospace;font-size:11px;"
                "line-height:1.6;padding:8px 12px;"
                "border-radius:8px 8px 2px 8px;"
            )
        else:
            bubble.setStyleSheet(
                "background:#0f0f0f;border:1px solid rgba(201,168,76,0.13);color:#d4d4d4;"
                "font-family:'Courier New',monospace;font-size:11px;"
                "line-height:1.6;padding:8px 12px;"
                "border-radius:2px 8px 8px 8px;"
            )
 
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
 
        layout.addWidget(lbl)
        layout.addLayout(row)
 
 
class TypingIndicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dots = 0
        self.setStyleSheet(
            "color:rgba(201,168,76,0.4);font-family:'Courier New',monospace;"
            "font-size:11px;padding:8px 12px;"
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()
 
    def start(self):
        self._dots = 0
        self.show()
        self._timer.start(400)
 
    def stop(self):
        self._timer.stop()
        self.hide()
 
    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self.setText("HELENA  " + "." * self._dots)
 
 
class ChatInterface(QWidget):
    response_received = Signal(str)
 
    def __init__(self, kernel, parent=None):
        super().__init__(parent)
        self.kernel = kernel
        self._worker = None
        self._build_ui()
 
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
 
        # Header bar
        header = QWidget()
        header.setFixedHeight(38)
        header.setStyleSheet("background:#0e0e0e;border-bottom:1px solid #1a1a1a;")
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 16, 0)
        dot = QFrame()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet("background:#c9a84c;border-radius:3px;")
        hlbl = QLabel("CONVERSATION")
        hlbl.setStyleSheet(
            "color:#c9a84c;font-family:'Courier New',monospace;"
            "font-size:9px;letter-spacing:3px;"
        )
        h.addWidget(dot)
        h.addWidget(hlbl)
        h.addStretch()
        layout.addWidget(header)
 
        # Scroll area for messages
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea{background:#080808;border:none;}"
            "QScrollBar:vertical{background:#080808;width:4px;border:none;}"
            "QScrollBar::handle:vertical{background:#1a1a1a;border-radius:2px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
 
        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background:#080808;")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(16, 16, 16, 16)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch()
 
        self._typing = TypingIndicator()
        self._msg_layout.addWidget(self._typing)
 
        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll, stretch=1)
 
        # Input bar
        input_bar = QWidget()
        input_bar.setFixedHeight(52)
        input_bar.setStyleSheet("background:#080808;border-top:1px solid #1a1a1a;")
        i = QHBoxLayout(input_bar)
        i.setContentsMargins(16, 8, 16, 8)
        i.setSpacing(8)
 
        self._input = QLineEdit()
        self._input.setPlaceholderText("enter message...")
        self._input.setStyleSheet(
            "QLineEdit{background:#0f0f0f;border:1px solid #2a2a2a;color:#ccc;"
            "font-family:'Courier New',monospace;font-size:11px;"
            "padding:6px 12px;border-radius:4px;}"
            "QLineEdit:focus{border:1px solid rgba(201,168,76,0.3);}"
        )
        self._input.returnPressed.connect(self._send)
 
        self._btn = QPushButton("SEND")
        self._btn.setFixedWidth(64)
        self._btn.setStyleSheet(
            "QPushButton{background:none;border:1px solid rgba(201,168,76,0.35);"
            "color:#c9a84c;font-family:'Courier New',monospace;font-size:10px;"
            "letter-spacing:2px;padding:6px 10px;border-radius:4px;}"
            "QPushButton:hover{background:rgba(201,168,76,0.08);}"
            "QPushButton:pressed{background:rgba(201,168,76,0.15);}"
            "QPushButton:disabled{border:1px solid #1a1a1a;color:#333;}"
        )
        self._btn.clicked.connect(self._send)
 
        i.addWidget(self._input)
        i.addWidget(self._btn)
        layout.addWidget(input_bar)
 
    def _send(self):
        text = self._input.text().strip()
        if not text or self._worker:
            return
        self._input.clear()
        self._add_message(text, "user")
        self._set_busy(True)
        self._worker = ChatWorker(self.kernel, text)
        self._worker.response_ready.connect(self._on_response)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()
 
    def _on_response(self, text):
        self._set_busy(False)
        self._add_message(text, "helena")
        self.response_received.emit(text)
 
    def _on_error(self, err):
        self._set_busy(False)
        self._add_message(f"Error: {err}", "helena")
 
    def _set_busy(self, busy):
        self._btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if busy:
            self._typing.start()
        else:
            self._typing.stop()
 
    def _add_message(self, text, role):
        bubble = MessageBubble(text, role)
        count = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, bubble)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
