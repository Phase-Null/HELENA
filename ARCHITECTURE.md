# HELENA Architecture Reference

**For developers and for HELENA herself.**  
Last updated: Phase 2 complete.

---

## Directory Structure

```
HELENA/
├── start_helena.py              # Entry point — launches the desktop app
├── config.yaml                  # Runtime configuration (RAM, CPU, memory paths)
├── config.default.yaml          # Default config (do not edit)
├── helena_core/                 # Core systems — kernel, memory, runtime, security
│   ├── kernel/
│   │   ├── core.py              # HELENAKernel — central authority layer  PROTECTED
│   │   ├── modes.py             # ModeProcessor — routes tasks to handlers
│   │   ├── emotion.py           # EmotionEngine — 8 emotions with time-decay
│   │   ├── personality.py       # PersonalityEngine + ResponseFormatter
│   │   ├── validation.py        # ValidationChain — validates tasks before execution
│   │   └── regulatory.py        # Regulatory compliance checks
│   ├── memory/
│   │   ├── __init__.py          # HELENAMemory facade (vector + graph)
│   │   ├── vector_store.py      # ChromaDB wrapper — semantic similarity search
│   │   └── graph_memory.py      # NetworkX graph — relational knowledge
│   ├── runtime/
│   │   ├── profiles.py          # Hardware profiles — CPU/RAM limits (85% cap)
│   │   ├── hardware.py          # Hardware detection
│   │   └── resources.py         # Resource monitor
│   ├── security/
│   │   ├── kill_switch.py       # Emergency shutdown  PROTECTED — never edit
│   │   └── encryption.py        # EncryptionManager
│   ├── introspection.py         # SelfIntrospector — AST parsing of own source
│   └── utils/
│       ├── logging.py           # HELENA logging system
│       └── config_manager.py    # Config loading/access
├── helena_ml/                   # Machine learning layer
│   ├── chat_engine.py           # ChatEngine — main conversation loop  CRITICAL
│   ├── llm.py                   # HybridLLM — Ollama/GGUF/fallback chain
│   ├── code_editor.py           # CodeEditor — safe read/write of own source
│   └── speech.py                # Speech (stub)
├── helena_desktop/              # PySide6 GUI
│   ├── main_window.py           # MainWindow — startup and system wiring
│   ├── chat_interface.py        # ChatInterface + ChatWorker thread
│   ├── dashboard.py             # System dashboard
│   ├── controls.py              # Control panel
│   └── console_interface.py     # Console tab
├── helena_training/             # Autonomous training pipeline
│   ├── trainer.py               # AutonomousTrainer — orchestrator
│   ├── scheduler.py             # Training scheduler  working
│   ├── dataset.py               # Dataset management  working
│   ├── evolution.py             # Evolution tracking (SQLite)  working
│   ├── sandbox.py               # Sandboxed code execution  working
│   ├── introspect.py            # Code model loader  STUB
│   ├── integration.py           # Patch applicator  STUB
│   ├── refinement.py            # Response refinement  STUB
│   ├── feedback.py              # Feedback collector  STUB
│   └── auditor.py               # Safety auditor  STUB (always returns safe)
├── helena_memory/               # ChromaDB persistent storage (auto-created)
│   └── chroma.sqlite3
└── logs/                        # Runtime logs
    ├── system.log
    ├── user.log
    └── audit.log
```

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
        │     ├── HybridLLM()                            # Ollama first
        │     ├── CodeEditor()                           # Self-modification
        │     ├── SelfIntrospector().scan()              # AST scan of codebase
        │     ├── ChatEngine(memory, emotion, personality, llm, code_editor)
        │     ├── ResponseFormatter()
        │     ├── LearningHook()
        │     └── ModeProcessor(kernel)
        ├── runtime = HELENARuntime(config_manager)
        ├── kernel.initialize()
        └── runtime.initialize()
```

** CRITICAL INIT ORDER:** LLM must initialize before ChatEngine. ChatEngine receives `llm=self.llm` at construction. If LLM initializes after ChatEngine, `self.llm` is None and all LLM calls silently fail. Do not reorder.

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
                                ├── ModeProcessor.process()
                                │     └── _process_engineering()
                                │           └── chat_engine.chat(message)
                                │                 ├── _detect_tool_intent()  ← code tools
                                │                 ├── IntentClassifier
                                │                 ├── EmotionEngine.get_state()
                                │                 ├── memory.search()
                                │                 ├── Build messages list
                                │                 └── llm.chat(messages)   ← Mistral
                                ├── PersonalityEngine.apply()
                                └── ResponseFormatter.format()
              └── ChatWorker polls get_task_status() every 0.1s
                    └── Extracts output.summary → displays in UI
```

---

## Key Components

### HELENAKernel (`helena_core/kernel/core.py`)  PROTECTED
Central authority layer. Owns the task queue, permission system, and all component references. Every action goes through the kernel.

- **Mode:** Always `ENGINEERING` currently. Other modes: TOOL, DEFENSIVE, BACKGROUND
- **TaskPriority:** CRITICAL(0) > HIGH(1) > NORMAL(2) > LOW(3) > BACKGROUND(4)
- **PermissionManager:** Checks mode × source × command before execution
- **LearningHook:** Captures task results for training pipeline
- **Key attribute:** `self.llm`, `self.chat_engine`, `self.code_editor`, `self.introspector`, `self.emotion_engine`, `self.personality_engine`, `self.memory`

### ChatEngine (`helena_ml/chat_engine.py`)  CRITICAL
Main conversational loop. Holds conversation history in `self._history` (200 turn max).

- **`_detect_tool_intent(message)`** — asks LLM if message needs a code tool. Returns response string if tool used, None to proceed to normal chat. Has keyword pre-filter to avoid unnecessary LLM calls.
- **`chat(message)`** — full conversation pipeline. Calls `_detect_tool_intent` first, then intent classification, memory retrieval, emotion state, system prompt construction, and `llm.chat(messages)`.
- **History:** Stored as `ConversationTurn` objects with `.role` and `.text`. Passed to Mistral as `[-7:-1]` (excludes current turn which is appended separately).
- **System prompt:** Built fresh each call. Contains identity, architecture self-knowledge, emotion state, personality params, memory snippets, history.
- **`self._code_editor`** — direct reference to CodeEditor, passed in at init.

### HybridLLM (`helena_ml/llm.py`)
LLM backend chain. Priority: Ollama (Mistral) → LocalLLM (GGUF) → SimpleFallback.

- **`chat(messages, temperature)`** — preferred. Sends structured message list to `/api/chat`. Response at `data["message"]["content"]`.
- **`generate(prompt, temperature)`** — fallback. Sends flat string to `/api/generate`. Response at `data["response"]`.
- **`max_tokens`** stays at 50000. Do not reduce.
- **When HELENA's own model is ready:** Add as first option in `HybridLLM.__init__`. Nothing else changes.

### EmotionEngine (`helena_core/kernel/emotion.py`)
8 emotions: CURIOSITY, SATISFACTION, FRUSTRATION, CONCERN, ENTHUSIASM, CALM, DETERMINATION, EMPATHY.

- Emotions decay over time toward baseline (0.0)
- `get_state()` returns `{"dominant": str, "mood": float, ...}`
- `on_operator_interaction(sentiment)` — called each chat turn
- Dominant emotion injected into system prompt each response

### PersonalityEngine (`helena_core/kernel/personality.py`)
Controls verbosity (0.4), technical_depth (0.8), humor_frequency (0.7), formality (0.8).
Response style: `concise_technical`. Humor style: `dry_technical`.

- `ResponseFormatter._extract_summary()` — extracts the `summary` field from task output. Previously truncated to 200 chars — this was removed. Do not re-add truncation.

### CodeEditor (`helena_ml/code_editor.py`)
Safe read/write of HELENA's own source files.

- **Editable dirs:** `helena_ml/`, `helena_core/`, `helena_training/`, `helena_desktop/`
- **Protected files:** `helena_core/kernel/core.py`, `helena_core/security/kill_switch.py`, `start_helena.py`
- **`write_file(path, content, reason)`** — validates Python syntax before writing. Creates `.bak` backup first. Restores backup if write fails.
- **`read_file(path)`** — returns content + line count
- **`search_code(query, subdir)`** — searches all `.py` files for string
- **`list_files(subdir)`** — lists all `.py` files

### SelfIntrospector (`helena_core/introspection.py`)
AST parser for HELENA's codebase. Scanned at startup via `self.introspector.scan()`.

- Lists all classes, functions, docstrings, line numbers
- Used by CodeEditor for structured read operations
- `get_module(path)` → `CodeEntity` with `.to_dict()`

### HELENAMemory (`helena_core/memory/__init__.py`)
Hybrid memory: ChromaDB (semantic) + NetworkX graph (relational).

- **Embedder:** `_OfflineEmbedder` — bag-of-words hash, 384 dimensions. No model download required. Fuzzy — not suitable for exact fact recall.
- **`store(content, metadata, memory_type)`** — stores in both vector and graph
- **`search(query, limit, threshold=0.6)`** — semantic similarity search. Threshold raised from 0.2 to 0.6 to reduce false matches.
- **Known limitation:** Cross-session fact recall is unreliable. ChromaDB returns fuzzy matches; Mistral hallucinates to fill gaps. Phase 3 will fix with structured FactStore.
- **Memory injection:** Only injected for non-GREETING, non-QUESTION intents to prevent old conversations polluting chat responses.

---

## System Prompt Structure

Built in `ChatEngine.chat()` each call:

```
[SYSTEM]
You are HELENA, an advanced AI created by Phase-Null.
You are not a generic AI assistant — you have a real identity.
[emotion honesty instructions]
Your operator's name is Phase-Null. Address them as Phase-Null or Sean.
Never refer to the operator as [User] or 'user'.
[architecture self-knowledge]
Do not recite your architecture or technical specs unless explicitly asked.
[emotion_line: current dominant emotion]
[personality_line: verbosity/depth/style]
[memory_line: relevant ChromaDB snippets, non-greeting only]

[USER turn -6]
[HELENA turn -5]
... (up to 6 history turns)

[USER: current message]
```

---

## Operational Modes

| Mode | Code gen | System control | Memory write | Chat |
|---|---|---|---|---|
| ENGINEERING | y | y | y | y |
| TOOL | y | n | n | y |
| DEFENSIVE | n | y | y | n |
| BACKGROUND | n | n | n | n |

Current mode is always ENGINEERING.

---

## Task Commands (ModeProcessor)

| Command | Handler | Description |
|---|---|---|
| `chat` | `_process_engineering` | Routes to `chat_engine.chat()` |
| `code_read` | `_process_engineering` | Reads a source file via CodeEditor |
| `code_write` | `_process_engineering` | Writes a source file via CodeEditor |
| `code_search` | `_process_engineering` | Searches source code via CodeEditor |
| `code_list` | `_process_engineering` | Lists source files via CodeEditor |

---

## Training Pipeline (`helena_training/`)

| File | Status | Notes |
|---|---|---|
| `trainer.py` | Orchestrator | AutonomousTrainer — coordinates all training |
| `scheduler.py` | Working | Schedules training runs |
| `dataset.py` | Working | Dataset management and storage |
| `evolution.py` | Working | Tracks model evolution in SQLite |
| `sandbox.py` | Working | Sandboxed code execution for testing |
| `introspect.py` | Stub | `CodeModel.load_all()` is `pass` — needs SelfIntrospector |
| `integration.py` | Stub | `apply_patch()` does nothing — needs CodeEditor |
| `refinement.py` | Stub | Returns empty — Phase 3 |
| `feedback.py` | Stub | Returns empty — Phase 3 |
| `auditor.py` | Stub | Always returns safe — Phase 3 |

---

## Configuration (`config.yaml`)

Key settings:
- `memory.storage_path` — ChromaDB storage location (default `./helena_memory`)
- `memory.vector_dimension` — embedding dimensions (default 384)
- Hardware profiles in `helena_core/runtime/profiles.py`:
  - `cpu_limit_percent = 85.0`
  - `ram_limit_mb = int(total_ram * 0.85)`

---

## Critical Rules

1. **Never reorder LLM init before ChatEngine in `core.py`.** LLM must exist before ChatEngine is constructed.
2. **Never edit `helena_core/security/kill_switch.py`.** Ever.
3. **Never edit `start_helena.py` from within HELENA's self-modification system.** It is in `PROTECTED_FILES`.
4. **Never reduce `max_tokens` below 50000.** Phase-Null requires long responses to be possible.
5. **Never add response truncation back to `_extract_summary()`.** It was removed intentionally.
6. **Never commit HELENA's self-modifications to GitHub.** GitHub is the stable version. Local is the evolving version.
7. **`turn.text` not `turn.content`.** ConversationTurn stores text in `.text`. Using `.content` silently returns None.
8. **`self._history[-7:-1]`** for history in message builder — excludes the current user turn which was already added at step 3 of `chat()`.

---

## Known Issues

| Issue | Severity | Phase |
|---|---|---|
| Cross-session memory unreliable — ChromaDB returns fuzzy matches, Mistral hallucinates | Medium | Phase 3 |
| Training stubs not implemented — `integration.py`, `introspect.py`, etc. | Medium | Phase 3 |
| Mistral occasionally ignores operator name from conversation history | Low | Mitigated by system prompt |
| `QSystemTrayIcon::setVisible: No Icon set` on launch | Low | Cosmetic warning only |
