"""
Command console for low-level system control
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton
from PySide6.QtGui import QFont, QTextCursor, QColor
from PySide6.QtCore import Qt
import json

class ConsoleInterface(QWidget):
    def __init__(self, kernel, runtime):
        super().__init__()
        self.kernel = kernel
        self.runtime = runtime
        
        layout = QVBoxLayout(self)
        
        # Console output
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Courier New", 9))
        self.output.setTextColor(QColor("#00FF00"))
        self.output.setStyleSheet("background-color: black;")
        layout.addWidget(self.output)
        
        # Command input
        input_layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter command (help for list)")
        self.input.returnPressed.connect(self.execute_command)
        input_layout.addWidget(self.input)
        
        self.exec_btn = QPushButton("Execute")
        self.exec_btn.clicked.connect(self.execute_command)
        input_layout.addWidget(self.exec_btn)
        
        layout.addLayout(input_layout)
        
        self.print_message("HELENA Console ready. Type 'help' for commands.", "system")
    
    def print_message(self, text, msg_type="info"):
        color = {
            "info": "#00FF00",
            "error": "#FF0000",
            "warning": "#FFFF00",
            "system": "#00AAFF",
            "command": "#FFFFFF"
        }.get(msg_type, "#00FF00")
        
        self.output.setTextColor(QColor(color))
        self.output.append(f"> {text}")
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output.setTextCursor(cursor)
    
    def execute_command(self):
        cmd = self.input.text().strip()
        if not cmd:
            return
        
        self.print_message(f"$ {cmd}", "command")
        self.input.clear()
        
        parts = cmd.split()
        if not parts:
            return
        
        command = parts[0].lower()
        args = parts[1:]
        
        try:
            if command == "help":
                self.print_message("Available commands:", "system")
                self.print_message("  status              - Show system status", "system")
                self.print_message("  mode [engineering|tool|defensive|background] - Change mode", "system")
                self.print_message("  profile [idle|background|normal|defense|turbo] - Switch performance profile", "system")
                self.print_message("  memory stats        - Show memory stats", "system")
                self.print_message("  clear               - Clear console", "system")
            
            elif command == "status":
                status = self.kernel.get_system_status()
                self.print_message(json.dumps(status, indent=2), "info")
            
            elif command == "mode":
                if not args:
                    self.print_message("Usage: mode [engineering|tool|defensive|background]", "error")
                else:
                    from helena_core.kernel import OperationalMode
                    mode_map = {
                        "engineering": OperationalMode.ENGINEERING,
                        "tool": OperationalMode.TOOL,
                        "defensive": OperationalMode.DEFENSIVE,
                        "background": OperationalMode.BACKGROUND
                    }
                    if args[0] in mode_map:
                        result = self.kernel.change_mode(mode_map[args[0]])
                        self.print_message(f"Mode changed: {result}", "info")
                    else:
                        self.print_message(f"Invalid mode: {args[0]}", "error")
            
            elif command == "profile":
                if not args:
                    self.print_message("Usage: profile [idle|background|normal|defense|turbo]", "error")
                else:
                    result = self.runtime.switch_profile(args[0].upper())
                    self.print_message(f"Profile switch: {result}", "info")
            
            elif command == "memory" and args and args[0] == "stats":
                stats = self.memory.get_stats() if hasattr(self, 'memory') else {}
                self.print_message(f"Memory stats: {stats}", "info")
            
            elif command == "clear":
                self.output.clear()
            
            else:
                self.print_message(f"Unknown command: {command}", "error")
        
        except Exception as e:
            self.print_message(f"Error: {e}", "error")