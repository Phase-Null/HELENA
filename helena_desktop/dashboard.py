"""
Real-time system monitoring dashboard with training status.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QGroupBox, QTableWidget, QTableWidgetItem
from PySide6.QtCore import QTimer, Qt
import psutil

class Dashboard(QWidget):
    def __init__(self, kernel, runtime, memory):
        super().__init__()
        self.kernel = kernel
        self.runtime = runtime
        self.memory = memory

        layout = QVBoxLayout(self)

        # System status
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout()
        self.mode_label = QLabel("Mode: ENGINEERING")
        status_layout.addWidget(self.mode_label)

        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel("CPU:"))
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        cpu_layout.addWidget(self.cpu_bar)
        status_layout.addLayout(cpu_layout)

        ram_layout = QHBoxLayout()
        ram_layout.addWidget(QLabel("RAM:"))
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        ram_layout.addWidget(self.ram_bar)
        status_layout.addLayout(ram_layout)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Kernel metrics
        kernel_group = QGroupBox("Kernel Metrics")
        kernel_layout = QVBoxLayout()
        self.tasks_label = QLabel("Tasks Processed: 0")
        kernel_layout.addWidget(self.tasks_label)
        self.success_label = QLabel("Success Rate: 0%")
        kernel_layout.addWidget(self.success_label)
        self.avg_time_label = QLabel("Avg Response Time: 0ms")
        kernel_layout.addWidget(self.avg_time_label)
        kernel_group.setLayout(kernel_layout)
        layout.addWidget(kernel_group)

        # Memory stats
        memory_group = QGroupBox("Memory")
        memory_layout = QVBoxLayout()
        self.mem_count_label = QLabel("Memories: 0")
        memory_layout.addWidget(self.mem_count_label)
        memory_group.setLayout(memory_layout)
        layout.addWidget(memory_group)

        # Gaming status
        self.gaming_label = QLabel("Gaming Mode: Inactive")
        layout.addWidget(self.gaming_label)

        # Training status
        training_group = QGroupBox("Training")
        training_layout = QVBoxLayout()
        self.train_enabled_label = QLabel("Enabled: No")
        training_layout.addWidget(self.train_enabled_label)
        self.last_session_label = QLabel("Last session: Never")
        training_layout.addWidget(self.last_session_label)
        self.improvements_label = QLabel("Improvements: 0")
        training_layout.addWidget(self.improvements_label)
        training_group.setLayout(training_layout)
        layout.addWidget(training_group)

        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(2000)

    def update_stats(self):
        try:
            status = self.kernel.get_system_status()
            self.mode_label.setText(f"Mode: {status.get('mode', 'UNKNOWN')}")
            metrics = status.get('metrics', {})
            self.tasks_label.setText(f"Tasks Processed: {metrics.get('tasks_processed', 0)}")
            success = metrics.get('success_rate', 0) * 100
            self.success_label.setText(f"Success Rate: {success:.1f}%")
            avg_time = metrics.get('avg_processing_time', 0) * 1000
            self.avg_time_label.setText(f"Avg Response Time: {avg_time:.1f}ms")

            sys_status = self.runtime.get_system_status()
            resources = sys_status.get('resources', {})
            self.cpu_bar.setValue(int(resources.get('cpu_percent', 0)))
            self.ram_bar.setValue(int(resources.get('ram_percent', 0)))

            gaming = sys_status.get('gaming', {})
            if gaming.get('active'):
                self.gaming_label.setText(f"Gaming Mode: Active ({gaming.get('game', 'Unknown')})")
                self.gaming_label.setStyleSheet("color: orange;")
            else:
                self.gaming_label.setText("Gaming Mode: Inactive")
                self.gaming_label.setStyleSheet("")

            mem_stats = self.memory.get_stats()
            self.mem_count_label.setText(f"Memories: {mem_stats.get('vector_store', {}).get('total_memories', 0)}")

            # Training status if available
            if hasattr(self.kernel, 'training') and self.kernel.training:
                tstatus = self.kernel.training.get_status()
                self.train_enabled_label.setText(f"Enabled: {'Yes' if tstatus['enabled'] else 'No'}")
                if tstatus['last_session_time']:
                    import time
                    self.last_session_label.setText(f"Last session: {time.ctime(tstatus['last_session_time'])}")
                else:
                    self.last_session_label.setText("Last session: Never")
                self.improvements_label.setText(f"Improvements: {sum(tstatus['improvement_stats'].values())}")
        except Exception as e:
            print(f"Dashboard update error: {e}")
