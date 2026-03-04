
---

## **Document 5: `training_integration.md`**

```markdown
# HELENA Self‑Training System – Integration with Core

This document describes how the training system connects with the kernel, runtime, memory, and modules, and how the operator interacts with it.

## 1. Kernel Integration

### Learning Hooks

The kernel's `LearningHook` class already provides a mechanism to register callbacks after each task execution. The training system registers a hook that:

- Extracts relevant data: `command`, `parameters`, `result`, `performance_metrics`, `success` flag.
- Adds the data to the `TrainingDataset` (type `kernel_tasks`).

### Training Interface

The kernel exposes a `training` attribute (an instance of `AutonomousTrainer`) after the training system is initialized. This allows the kernel to:

- Start/stop training sessions via kernel commands (e.g., when operator uses `helena train enable`).
- Provide training status in `get_system_status()`.

### Permission Matrix

Add the following commands to `permission_matrix` in `kernel/core.py` (for ENGINEERING mode):

```python
"training_enable": True,
"training_disable": True,
"training_start": True,
"training_status": True,