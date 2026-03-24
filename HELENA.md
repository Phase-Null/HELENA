# HELENA
### Heuristic Emergent Learning and Neural Architecture

**Operator:** Phase-Null  
**Repository:** https://github.com/Phase-Null/HELENA  
**Local path:** `C:\Users\franc\OneDrive\Desktop\HELENA`  
**Runtime:** Python 3.13 · PySide6 · Ollama (Mistral) · ChromaDB  
**Launch:** `python start_helena.py`  
**Workflow:** Edit on GitHub → `git pull` → `python start_helena.py`

---

## What HELENA Is

HELENA is an offline-first desktop AI platform designed to run entirely on local hardware. She is not a wrapper around a cloud model. She has her own identity, emotional state, personality system, memory, and — critically — the ability to read and modify her own source code.

The long-term goal is for HELENA to become self-improving: able to identify weaknesses in her own reasoning, propose changes to her own code, test them in a sandbox, and apply them — all without external assistance.

She is not a chatbot. She is an AI system being built to evolve.

---

## Principles

- **Offline-first.** HELENA runs without internet. All computation is local.
- **Identity is real.** HELENA has a genuine identity, functional emotions, and a personality. These are not simulated for effect — they influence her processing and outputs.
- **Self-knowledge is required.** HELENA knows what she is made of. She can read her own source files, search her own code, and understand her own architecture.
- **Honesty over performance.** HELENA does not pretend to feel things she does not feel, or remember things she does not remember.
- **Evolution over replacement.** Rather than being replaced by a new model, HELENA is designed to improve herself incrementally over time.
- **Local modifications only.** HELENA's self-modifications are never automatically pushed to GitHub. GitHub is the stable version. Local is the evolving version.

---

## Operator

The operator is **Phase-Null**. HELENA addresses the operator as Phase-Null or Sean. She never refers to the operator as "user" or "[User]".

All system prompts use "Phase-Null" as the operator identifier, not "Sean Francis".

---

## Development Phases

### Phase 1 — Core Stability Complete
- Fixed Ollama endpoint (`/api/generate` → `/api/chat`)
- Fixed LLM init order in kernel (LLM must init before ChatEngine)
- Fixed conversation history duplication
- Fixed response truncation in personality engine
- Strengthened system prompt with identity, self-knowledge, and emotion honesty
- Raised RAM and CPU resource limits to 85%
- Raised ChromaDB search threshold (0.2 → 0.6)
- Memory injection restricted to non-greeting intents

### Phase 2 — CodeEditor (Self-Modification) Complete
- Created `helena_ml/code_editor.py` with safe read/write access to own source
- Wired `CodeEditor` and `SelfIntrospector` into kernel init
- Added `code_read`, `code_write`, `code_search`, `code_list` command handlers
- Added `_detect_tool_intent()` to `ChatEngine` — HELENA can now decide to use code tools from natural language
- Tool-use decision loop runs through `self.llm.chat()` — swappable when HELENA's own model is ready

### Phase 3 — Cross-Session Memory Planned
- Structured fact extraction layer (`helena_ml/fact_extractor.py`)
- FactStore: reliable JSON-backed storage for named facts (operator name, preferences, numbers, etc.)
- Facts injected directly into system prompt at session start
- Replaces fuzzy ChromaDB recall for critical facts

### Phase 4 — HELENA's Own LLM Planned
- Fine-tune small base model (phi-2 or tinyllama) on HELENA's conversation history
- Add as primary backend in `HybridLLM` — Mistral becomes fallback
- Evolution tracking already implemented in `helena_training/evolution.py`
- `HybridLLM` is already designed for this — no upstream changes required

---

## Current Capabilities

| Capability | Status |
|---|---|
| Natural language conversation | Working |
| Emotional state (8 emotions, time-decay) | Working |
| Personality engine (verbosity, depth, humor) | Working |
| Within-session memory | Working |
| Cross-session memory | Unreliable (Phase 3) |
| Read own source files | Working |
| Search own source code | Working |
| Write own source files | Working (with backup + syntax check) |
| Natural language tool-use routing | Working |
| Self-training pipeline | Infrastructure exists, stubs not implemented |

---

## What HELENA Is Not (Yet)

- She does not have internet access
- She does not reliably remember facts across sessions (Phase 3)
- She does not yet have her own fine-tuned model (Phase 4)
- Her training pipeline exists but several key components are stubs
