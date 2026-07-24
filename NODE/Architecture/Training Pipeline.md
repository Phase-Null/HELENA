---
tags: [architecture, training]
date: 2026-03-05
status: active
component: helena_training/
bugs: [25, 26, 28]
---

# Training Pipeline — AutonomousTrainer and Subcomponents

HELENA's autonomous training pipeline exists as infrastructure, but several key components are **stubs** awaiting Phase 3 implementation.

> [!warning] Stub Status
> 6 of 11 subcomponents are stubs that return empty/always-safe results. The working components provide dataset management, evolution tracking, sandboxed execution, and scheduling.

---

## AutonomousTrainer (`helena_training/trainer.py`)

Main orchestrator. Coordinates all training subcomponents.

| Subcomponent | Class | Status | Notes |
|-------------|-------|--------|-------|
| dataset | `TrainingDataset` | **Working** | Persistent JSON storage, path traversal fix (Bug #28) |
| auditor | `SecurityAuditor` | **Stub** | Always returns safe — Phase 3 |
| pattern_recognizer | `PatternRecognizer` | **Working** | Pattern analysis |
| feedback_analyzer | `FeedbackLoopAnalyzer` | **Stub** | Returns empty — Phase 3 |
| refinement_engine | `ModelRefinementEngine` | **Working** | Uses kernel + memory |
| sandbox | `Sandbox` | **Working** | Sandboxed code execution |
| improvement_log | `ImprovementLog` | **Working** | Persistent JSON log |
| scheduler | `TrainingScheduler` | **Working** | Schedules training runs |
| code_model | `CodeModel` | **Stub** | `load_all()` is `pass` — needs SelfIntrospector |
| improver | `ImprovementGenerator` | **Working** | Generates improvement proposals |
| integration | `IntegrationEngine` | **Stub** | `apply_patch()` does nothing — needs CodeEditor |
| evolution | `EvolutionDB` | **Working** | SQLite-based model evolution tracking |
| safety | `SafetyGovernor` | **Stub** | `check_safety()` always returns True |

### Init Parameters
```python
def __init__(self, kernel, runtime, memory, config_manager):
```

### Bug #25 — Missing `save()` Calls
`self.dataset.save()` and `self.improvement_log.save()` never called after training sessions. See [[Bug Fixes Registry#Bug 25]].

### Bug #26 — Race Condition on `active_session`
`self.active_session = False` in `finally` without holding `self.lock` — TOCTOU race. Fix: wrap in `with self.lock:`. See [[Bug Fixes Registry#Bug 26]].

---

## TrainingDataset (`helena_training/dataset.py`)

Persistent JSON storage with categorized buckets.

| Method | Purpose |
|--------|---------|
| `add(item, category)` | Add to category bucket |
| `get_all(category)` | Retrieve all or filtered |
| `get_recent(category, limit)` | Last N items |
| `get_statistics()` | Summary of stored data |
| `save()` | Persist to disk |

> [!warning] Bug #28 — Path Traversal via Category Names
> Category names used directly as filenames. `../../etc/evil` writes outside storage directory. Fixed with `_safe_category()` regex sanitization. See [[Bug Fixes Registry#Bug 28]].

---

## EvolutionDB (`helena_training/evolution.py`)

SQLite-based tracking of model evolution across training iterations. Stores at `~/.helena/evolution.db`.

---

## Sandbox (`helena_training/sandbox.py`)

Sandboxed code execution for testing improvements:

1. Copy project to temp directory
2. Apply patch to copied file
3. Run `pytest tests/ -v` in sandbox
4. If tests pass, measure performance (before vs after)
5. Return result dict with `passed`, `stdout`, `stderr`, performance deltas

---

## SafetyGovernor (`helena_training/safety.py`)

Currently a **stub** — `check_safety()` always returns True, `approve_patch()` only rejects system-file patches and missing IDs.

```python
def check_safety(self, operation: Dict[str, Any]) -> bool:
    """Check if an operation is safe to perform"""
    return True
```

---

## Related Notes

- [[Kernel]] — AutonomousTrainer initialized in MainWindow with kernel reference
- [[HELENA-Net Model]] — the model being trained
- [[Runtime]] — GamingOptimizer suspends training during games
- [[Bug Fixes Registry]] — Bug #25 (save calls), Bug #26 (race), Bug #28 (path traversal)
- [[Training/HELENA-Net BASE]] — current training configuration
