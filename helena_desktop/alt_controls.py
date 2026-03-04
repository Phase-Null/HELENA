"""
Control panel for HELENA settings and profiles
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QMessageBox
from PySide6.QtCore import Qt

class ControlsPanel(QWidget):
    def __init__(self, kernel, runtime, config_manager):
        super().__init__()
        self.kernel = kernel
        self.runtime = runtime
        self.config = config_manager
        
        layout = QVBoxLayout(self)
        
        # Performance profile
        profile_group = QGroupBox("Performance Profile")
        profile_layout = QVBoxLayout()
        
        self.profile_combo = QComboBox()
        profiles = ["IDLE", "BACKGROUND", "NORMAL", "DEFENSE", "TURBO"]
        for p in profiles:
            self.profile_combo.addItem(p)
        self.profile_combo.currentTextChanged.connect(self.change_profile)
        profile_layout.addWidget(self.profile_combo)
        
        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)
        
        # Resource limits
        limits_group = QGroupBox("Resource Limits (Operator Override)")
        limits_layout = QVBoxLayout()
        
        # CPU limit
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel("CPU %:"))
        self.cpu_spin = QDoubleSpinBox()
        self.cpu_spin.setRange(0, 100)
        self.cpu_spin.setValue(50)
        cpu_layout.addWidget(self.cpu_spin)
        limits_layout.addLayout(cpu_layout)
        
        # RAM limit (MB)
        ram_layout = QHBoxLayout()
        ram_layout.addWidget(QLabel("RAM (MB):"))
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 65536)
        self.ram_spin.setValue(4096)
        self.ram_spin.setSingleStep(512)
        ram_layout.addWidget(self.ram_spin)
        limits_layout.addLayout(ram_layout)
        
        # Apply button
        apply_btn = QPushButton("Apply Limits")
        apply_btn.clicked.connect(self.apply_limits)
        limits_layout.addWidget(apply_btn)
        
        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)
        
        # Learning toggle
        learn_group = QGroupBox("Learning")
        learn_layout = QVBoxLayout()
        
        self.learn_check = QCheckBox("Enable autonomous learning")
        self.learn_check.stateChanged.connect(self.toggle_learning)
        learn_layout.addWidget(self.learn_check)
        
        learn_group.setLayout(learn_layout)
        layout.addWidget(learn_group)
        
        # Security
        security_group = QGroupBox("Security")
        security_layout = QVBoxLayout()
        
        lockdown_btn = QPushButton("Emergency Lockdown")
        lockdown_btn.setStyleSheet("background-color: red; color: white;")
        lockdown_btn.clicked.connect(self.emergency_lockdown)
        security_layout.addWidget(lockdown_btn)
        
        security_group.setLayout(security_layout)
        layout.addWidget(security_group)
        
        layout.addStretch()
    
    def change_profile(self, profile_name):
        try:
            self.runtime.switch_profile(profile_name)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to switch profile: {e}")
    
    def apply_limits(self):
        limits = [
            {
                'type': 'CPU',
                'max_usage': self.cpu_spin.value(),
                'priority': 1,
                'action': 'throttle'
            },
            {
                'type': 'RAM',
                'max_usage': self.ram_spin.value(),
                'priority': 1,
                'action': 'suspend'
            }
        ]
        try:
            self.runtime.set_resource_limits(limits)
            QMessageBox.information(self, "Success", "Resource limits applied.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to apply limits: {e}")
    
    def toggle_learning(self, state):
        # This would enable/disable training
        pass
    
    def emergency_lockdown(self):
        reply = QMessageBox.question(
            self, "Emergency Lockdown",
            "This will freeze HELENA and clear all non-critical tasks. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.kernel.set_lockdown_mode(True)
            QMessageBox.information(self, "Lockdown", "HELENA is now in lockdown mode.")