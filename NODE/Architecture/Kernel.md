---
tags: [architecture, kernel]
date: 2026-03-05
status: active
component: helena_core/kernel/core.py
---

# Kernel — HELENAKernel Central Authority Layer

HELENAKernel is the central reasoning and authority layer. It owns the task queue, permission system, and all component references. Every action goes through the kernel. **PROTECTED** — never edit without full review.

> [!warning] Critical Init Order
> **LLM must initialize before ChatEngine.** ChatEngine receives `llm=self.llm` at construction. If LLM initializes after ChatEngine, `self.llm` is None and all LLM calls silently fail. **Do not reorder.**

---

## Startup Sequence

```
start_helena.py
  └── main_window.py MainWindow.__init__()
        ├── config_manager = get_config_manager()
        ├── memory = HELENAMemory(config_manager)        # ChromaDB + Graph
        ├── kernel = HELENAKernel("primary_operator", config_manager, memory)
        │     ├── PersonalityEngine()
        │     ├── EmotionEngine()
        │     ├── HybridLLM()                            # Ollama first ← MUST BE BEFORE ChatEngine
        │     ├── CodeEditor()                           # Self-modification
        │     ├── SelfIntrospector().scan()              # AST scan of codebase
        │     ├── ChatEngine(memory, emotion, personality, llm, code_editor)
        │     ├── ResponseFormatter()
        │     ├── LearningHook()
        │     ├── ModeProcessor(kernel)
        │     ├── RegulatoryCore()                        # 16 rules: 8 ABS + 5 OPR + 3 ADV
        │     └── AEGIS Security Bridge (if aegis_python available)
        ├── runtime = HELENARuntime(config_manager)
        ├── kernel.initialize()
        └── runtime.initialize()
```

---

## Key Data Structures

### `TaskPriority` (Enum)

| Level | Value | Use Case |
|-------|-------|----------|
| CRITICAL | 0 | Security, kill switch, emergency |
| HIGH | 1 | Operator commands, real-time responses |
| NORMAL | 2 | Module requests, background processing |
| LOW | 3 | Training, maintenance, cleanup |
| BACKGROUND | 4 | Idle-time processing |

### `TaskStatus` (Enum)

`PENDING → VALIDATING → PROCESSING → VALIDATED → EXECUTING → COMPLETED | FAILED | CANCELLED`

### `TaskContext` (dataclass)

| Field | Type | Purpose |
|-------|------|---------|
| `operator_id` | `str` | Who submitted the task |
| `session_id` | `str` | Session identifier |
| `source` | `str` | `'operator'`, `'module'`, `'system'`, `'training'` |
| `permissions` | `Set[str]` | Allowed operations |
| `resource_budget` | `Dict[str, Any]` | CPU, RAM, time limits |

---

## Operational Modes

| Mode | Code gen | System control | Memory write | Chat |
|------|----------|---------------|-------------|------|
| **ENGINEERING** | ✅ | ✅ | ✅ | ✅ |
| TOOL | ✅ | ❌ | ❌ | ✅ |
| DEFENSIVE | ❌ | ✅ | ✅ | ❌ |
| BACKGROUND | ❌ | ❌ | ❌ | ❌ |

Current mode is always **ENGINEERING**.

---

## Task Commands (ModeProcessor)

| Command | Handler | Description | Target |
|---------|---------|-------------|--------|
| `chat` | `_process_engineering` | Routes to [[Chat Engine|ChatEngine.chat()]] | Main conversation loop |
| `code_read` | `_process_engineering` | Reads a source file via CodeEditor | `CodeEditor.read_file(path)` |
| `code_write` | `_process_engineering` | Writes a source file via CodeEditor | `CodeEditor.write_file(path, content, reason)` |
| `code_search` | `_process_engineering` | Searches source code via CodeEditor | `CodeEditor.search_code(query, subdir)` |
| `code_list` | `_process_engineering` | Lists source files via CodeEditor | `CodeEditor.list_files(subdir)` |

---

## Chat Request Flow

```
User types message
  └── ChatInterface.send_message()
        └── ChatWorker(kernel, message).start()          # Background QThread
              └── kernel.submit_task("chat", {message})
                    └── TaskQueue → PermissionManager check
                          └── _process_single_task()
                                ├── ValidationChain.validate()
                                │     └── [[Personality System|RegulatoryCore]].check(task)
                                ├── ModeProcessor.process()
                                │     └── _process_engineering()
                                │           └── [[Chat Engine|chat_engine.chat(message)]]
                                │                 ├── _detect_tool_intent()
                                │                 ├── IntentClassifier
                                │                 ├── EmotionEngine.get_state()
                                │                 ├── memory.search()
                                │                 └── llm.chat(messages)
                                ├── PersonalityEngine.apply()
                                └── ResponseFormatter.format()
```

---

## Key Component References

| Attribute | Type | Description |
|-----------|------|-------------|
| `self.llm` | `HybridLLM` | LLM backend chain (Ollama → GGUF → Fallback) |
| `self.chat_engine` | `ChatEngine` | Main conversation handler |
| `self.code_editor` | `CodeEditor` | Safe self-modification access |
| `self.introspector` | `SelfIntrospector` | AST parser for own codebase |
| `self.emotion_engine` | `EmotionEngine` | 8-emotion state manager |
| `self.personality_engine` | `PersonalityEngine` | Verbose/depth/humor modulation |
| `self.memory` | `HELENAMemory` | Hybrid ChromaDB + NetworkX |
| `self.aegis` | `AegisBridge` | Optional AEGIS security bridge |

---

## Critical Rules

> [!danger] Never Violate These
> 1. **Never reorder LLM init before ChatEngine** — LLM must exist before ChatEngine construction
> 2. **Never edit `helena_core/security/kill_switch.py`** — Ever
> 3. **Never edit `start_helena.py`** from self-modification — it is in PROTECTED_FILES
> 4. **Never reduce `max_tokens` below 50000** — Phase-Null requires long responses
> 5. **Never add truncation back to `_extract_summary()`** — Removed intentionally
> 6. **Never commit self-modifications to GitHub** — Local is evolving, GitHub is stable
> 7. **`turn.text` not `turn.content`** — ConversationTurn stores text in `.text`
> 8. **`self._history[-7:-1]`** for history — excludes current turn already added

---

## Related Notes

- [[HELENA-Net Model]] — the model that will replace Mistral in HybridLLM
- [[Personality System]] — RegulatoryCore is wired into ValidationChain
- [[Chat Engine]] — receives `llm=self.llm` at construction
- [[Memory System]] — HELENAMemory facade used by kernel
- [[Runtime]] — ResourceManager initialized alongside kernel
- [[AEGIS/Overview]] — AEGIS bridge integration (optional)
