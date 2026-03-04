"""
Control panel for HELENA settings and profiles
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QTimeEdit, QMessageBox
from PySide6.QtCore import Qt, QTime

class ControlsPanel(QWidget):
    def __init__(self, kernel, runtime, config_manager, trainer=None):
        super().__init__()
        self.kernel = kernel
        self.runtime = runtime
        self.config = config_manager
        self.trainer = trainer  # may be None

        layout = QVBoxLayout(self)

        # Performance Profile
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

        # Resource Limits
        limits_group = QGroupBox("Resource Limits (Operator Override)")
        limits_layout = QVBoxLayout()
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel("CPU %:"))
        self.cpu_spin = QDoubleSpinBox()
        self.cpu_spin.setRange(0, 100)
        self.cpu_spin.setValue(50)
        cpu_layout.addWidget(self.cpu_spin)
        limits_layout.addLayout(cpu_layout)

        ram_layout = QHBoxLayout()
        ram_layout.addWidget(QLabel("RAM (MB):"))
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 65536)
        self.ram_spin.setValue(4096)
        self.ram_spin.setSingleStep(512)
        ram_layout.addWidget(self.ram_spin)
        limits_layout.addLayout(ram_layout)

        apply_btn = QPushButton("Apply Limits")
        apply_btn.clicked.connect(self.apply_limits)
        limits_layout.addWidget(apply_btn)

        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)

        # Training
        training_group = QGroupBox("Training")
        training_layout = QVBoxLayout()

        self.enable_training_cb = QCheckBox("Enable autonomous learning")
        self.enable_training_cb.stateChanged.connect(self.toggle_training)
        training_layout.addWidget(self.enable_training_cb)

        # Schedule settings
        schedule_layout = QHBoxLayout()
        schedule_layout.addWidget(QLabel("Daily time:"))
        self.daily_time_edit = QTimeEdit()
        self.daily_time_edit.setTime(QTime(2, 0))
        schedule_layout.addWidget(self.daily_time_edit)
        training_layout.addLayout(schedule_layout)

        weekly_layout = QHBoxLayout()
        weekly_layout.addWidget(QLabel("Weekly day:"))
        self.weekly_day_combo = QComboBox()
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for d in days:
            self.weekly_day_combo.addItem(d.capitalize())
        self.weekly_day_combo.setCurrentText("Sunday")
        weekly_layout.addWidget(self.weekly_day_combo)

        weekly_layout.addWidget(QLabel("Time:"))
        self.weekly_time_edit = QTimeEdit()
        self.weekly_time_edit.setTime(QTime(3, 0))
        weekly_layout.addWidget(self.weekly_time_edit)
        training_layout.addLayout(weekly_layout)

        idle_layout = QHBoxLayout()
        idle_layout.addWidget(QLabel("Idle minutes:"))
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(5, 120)
        self.idle_spin.setValue(30)
        idle_layout.addWidget(self.idle_spin)
        training_layout.addLayout(idle_layout)

        # Focus areas
        focus_label = QLabel("Focus areas:")
        training_layout.addWidget(focus_label)

        focus_layout = QHBoxLayout()
        self.focus_code = QCheckBox("Code")
        self.focus_efficiency = QCheckBox("Efficiency")
        self.focus_accuracy = QCheckBox("Accuracy")
        self.focus_security = QCheckBox("Security")
        self.focus_memory = QCheckBox("Memory")
        focus_layout.addWidget(self.focus_code)
        focus_layout.addWidget(self.focus_efficiency)
        focus_layout.addWidget(self.focus_accuracy)
        focus_layout.addWidget(self.focus_security)
        focus_layout.addWidget(self.focus_memory)
        training_layout.addLayout(focus_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.start_training_btn = QPushButton("Start Now")
        self.start_training_btn.clicked.connect(self.start_training)
        btn_layout.addWidget(self.start_training_btn)

        self.view_report_btn = QPushButton("View Report")
        self.view_report_btn.clicked.connect(self.view_report)
        btn_layout.addWidget(self.view_report_btn)
        training_layout.addLayout(btn_layout)

        training_group.setLayout(training_layout)
        layout.addWidget(training_group)

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
            {'type': 'CPU', 'max_usage': self.cpu_spin.value(), 'priority': 1, 'action': 'throttle'},
            {'type': 'RAM', 'max_usage': self.ram_spin.value(), 'priority': 1, 'action': 'suspend'}
        ]
        try:
            self.runtime.set_resource_limits(limits)
            QMessageBox.information(self, "Success", "Resource limits applied.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to apply limits: {e}")

    def toggle_training(self, state):
        if not self.trainer:
            QMessageBox.warning(self, "Training", "Training system not available.")
            return
        enabled = (state == Qt.Checked)
        if enabled:
            self.trainer.enable()
            QMessageBox.information(self, "Training", "Training enabled.")
        else:
            self.trainer.disable()
            QMessageBox.information(self, "Training", "Training disabled.")

    def start_training(self):
        if not self.trainer:
            QMessageBox.warning(self, "Training", "Training system not available.")
            return
        focus = []
        if self.focus_code.isChecked(): focus.append("code")
        if self.focus_efficiency.isChecked(): focus.append("efficiency")
        if self.focus_accuracy.isChecked(): focus.append("accuracy")
        if self.focus_security.isChecked(): focus.append("security")
        if self.focus_memory.isChecked(): focus.append("memory")
        if not focus:
            focus = ["default"]
        result = self.trainer.start_session(focus_areas=focus, reason="ui")
        QMessageBox.information(self, "Training", f"Session completed: {result}")

    def view_report(self):
        if not self.trainer:
            QMessageBox.warning(self, "Training", "Training system not available.")
            return
        # Simple report for now
        status = self.trainer.get_status()
        msg = f"Enabled: {status['enabled']}\nLast session: {status['last_session_time']}\nImprovements: {status['improvement_stats']}"
        QMessageBox.information(self, "Training Report", msg)

    def emergency_lockdown(self):
        reply = QMessageBox.question(self, "Emergency Lockdown", "This will freeze HELENA. Continue?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.kernel.set_lockdown_mode(True)
            QMessageBox.information(self, "Lockdown", "HELENA is now in lockdown mode.")
