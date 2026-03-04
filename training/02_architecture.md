# HELENA Self‑Training System – Architecture

## 1. Component Diagram
┌─────────────────┐
│ Kernel Hooks │
└────────┬────────┘
│ (task results)
▼
┌─────────────────┐ ┌─────────────────┐
│ Data Collector │────▶│ Security Auditor │
└─────────────────┘ └────────┬────────┘
│ (cleaned data)
▼
┌─────────────────┐ ┌─────────────────┐
│Pattern Recognizer│────▶│ Feedback Analyzer│
└─────────────────┘ └────────┬────────┘
│ (patterns)
▼
┌─────────────────┐ ┌─────────────────┐
│ Model Refinement│────▶│ Sandbox Tester │
└─────────────────┘ └────────┬────────┘
│ (validated improvements)
▼
┌─────────────────┐ ┌─────────────────┐
│Improvement Log │◀───▶│ Integrator │
└─────────────────┘ └────────┬────────┘
│ (applied to live system)
▼
┌─────────────────┐
│ Scheduler │
└─────────────────┘

## 2. Data Flow Description

1. **Kernel Hooks** – After each task completion (`TaskResult`), the `LearningHook` in the kernel captures relevant data (command, parameters, success/failure, performance metrics). This data is passed to the training system asynchronously.

2. **Data Collector** – Aggregates captured data into a structured format and stores it in the training dataset (separate from long‑term memory). It also collects:
   - Operator feedback (explicit ratings, corrections).
   - Resource usage logs from the runtime.
   - Error patterns from kernel error logs.

3. **Security Auditor** – Scans the aggregated data for:
   - Malicious code injection.
   - Attempts to exfiltrate sensitive information.
   - Data integrity issues (corrupted records).
   - Compliance with security policies (e.g., no personal data retention).

   If any issue is found, the entire batch is rejected and logged for operator review.

4. **Pattern Recognizer** – Applies clustering and sequence mining algorithms to identify:
   - Frequent command sequences that lead to success.
   - Common error patterns.
   - Operator style preferences (e.g., naming conventions, formatting).

5. **Feedback Analyzer** – Specialises in detecting positive and negative feedback loops:
   - A **positive loop** is a sequence where a decision consistently leads to good outcomes and reinforces itself.
   - A **negative loop** is an oscillating or stuck pattern (e.g., repeatedly trying the same failing approach).

   It suggests breaking negative loops and amplifying positive ones.

6. **Model Refinement** – Takes patterns and feedback to generate concrete improvements. These can be:
   - Tweaks to kernel decision parameters (e.g., confidence thresholds).
   - New heuristics for code generation.
   - Updates to memory retrieval weights.
   - Adjustments to personality verbosity based on operator feedback.

   Each improvement is packaged with metadata: type, expected impact, parameters changed.

7. **Sandbox Tester** – Runs the proposed improvements in an isolated environment (the same sandbox used for modules). It compares performance against a baseline (e.g., using a held‑out validation set) and checks for security compliance.

8. **Integrator** – If validation passes, it:
   - Creates a backup of the current system state.
   - Applies the improvements (e.g., updates kernel parameters, writes new memory entries).
   - Records the change in the `ImprovementLog`.
   - If any error occurs during integration, it rolls back to the backup.

9. **Improvement Log** – Stores a permanent record of all applied improvements, including timestamp, type, impact, and any relevant metrics. Used for reporting and auditing.

10. **Scheduler** – Orchestrates training sessions based on:
    - Operator‑defined schedule (e.g., nightly at 2 AM).
    - System idle detection (low CPU/GPU usage, no gaming).
    - Manual triggers from CLI or UI.

## 3. Threading Model

- The training system runs in a separate, low‑priority thread pool.
- During active training, it can be paused automatically if gaming mode is detected (via the runtime).
- The scheduler runs its own monitoring thread that checks conditions periodically.

## 4. Persistence

- Training datasets are stored in encrypted form in `~/.helena/training/`.
- Improvement logs are stored in `~/.helena/logs/training.log` (structured, encrypted).
- Backups are stored in `~/.helena/backups/` before each integration.
