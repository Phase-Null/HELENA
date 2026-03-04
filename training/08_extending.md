
---

## **Document 8: `training_extending.md`**

```markdown
# HELENA Self‑Training System – Extending with Custom Improvements

Developers can add new types of improvements to HELENA by implementing new `Improver` classes and registering them with the `ModelRefinementEngine`.

## 1. Overview

The training system is designed to be modular. Each `Improver` focuses on one aspect of the system (e.g., code generation, memory retrieval, decision making). To add a new capability:

1. Create a new class that inherits from a base `Improver` (or follow the interface of `SoftwareEngineeringImprover`).
2. Implement the method `generate_improvements(self, patterns, feedback_loops) -> List[Dict]`.
3. Register the improver in `ModelRefinementEngine.__init__`.

## 2. Improver Interface

An improver should:

- Accept a list of patterns (from `PatternRecognizer`) and a list of feedback loops (from `FeedbackLoopAnalyzer`).
- Analyse them to produce candidate improvements.
- Each improvement must be a dictionary with at least the following keys:

```python
{
    'id': str,                     # unique (can be generated)
    'type': str,                   # e.g., 'code_heuristic'
    'description': str,            # human-readable
    'parameters': dict,            # the actual change to apply
    'expected_impact': float,      # estimated improvement (0-1 scale)
    'requires_restart': bool,      # if true, system will suggest restart
    'security_risk': str,          # 'low', 'medium', 'high'
    'dependencies': list,          # other improvement IDs this depends on
}