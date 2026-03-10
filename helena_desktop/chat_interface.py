"""
Chat interface for interacting with HELENA
"""
import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor

from helena_core.kernel import TaskPriority

class ChatWorker(QThread):
    """Background thread for processing chat messages"""
    response_ready = Signal(dict)
    
    def __init__(self, kernel, message):
        super().__init__()
        self.kernel = kernel
        self.message = message
    
    def run(self):
        task_id = self.kernel.submit_task(
            command="chat",
            parameters={"message": self.message},
            source="operator",
            priority=TaskPriority.NORMAL
        )
        # Wait for result - should be fast now with simple fallback
        max_attempts = 300  # 300 * 0.1s = 30 seconds max
        for attempt in range(max_attempts):
            time.sleep(0.1)
            result = self.kernel.get_task_status(task_id)
            if result and result.get("status") == "completed":
                # Extract the actual output from the nested result
                task_result = result.get("result", {})
                if isinstance(task_result, dict):
                    output = task_result.get("result") or task_result.get("output") or str(task_result)
                else:
                    output = str(task_result)
                self.response_ready.emit({"output": output})
                return
        
        # Timeout (shouldn't happen with fallback)
        self.response_ready.emit({"error": "Response timeout"})

class ChatInterface(QWidget):
    def __init__(self, kernel):
        super().__init__()
        self.kernel = kernel
        
        layout = QVBoxLayout(self)
        
        # Chat display
        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.setFont(QFont("Courier", 10))
        layout.addWidget(self.display)
        
        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
        
        # Worker thread
        self.worker = None
    
    def send_message(self):
        msg = self.input_field.text().strip()
        if not msg:
            return
        
        self.display.append(f"<b>You:</b> {msg}")
        self.input_field.clear()
        
        # Disable input while processing
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        
        # Start background worker
        self.worker = ChatWorker(self.kernel, msg)
        self.worker.response_ready.connect(self.handle_response)
        self.worker.start()
    
    def handle_response(self, result):
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        
        if result:
            if 'error' in result:
                self.display.append(f"<b>HELENA:</b> Error: {result['error']}")
            elif 'output' in result:
                self.display.append(f"<b>HELENA:</b> {result['output']}")
            else:
                self.display.append(f"<b>HELENA:</b> (no response)")
        else:

            self.display.append(f"<b>HELENA:</b> (no response)")
