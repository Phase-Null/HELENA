---
tags: [architecture, chat]
date: 2026-03-05
status: active
component: helena_ml/chat_engine.py
bugs: [2, 16, 29]
---

# Chat Engine — Conversation Pipeline

ChatEngine is HELENA's main conversational loop. It handles intent classification, tool-use routing, memory retrieval, system prompt construction, and LLM dispatch. **CRITICAL** — the primary operator-facing component.

> [!info] Architecture
> `IntentClassifier → ContextBuilder → ResponseComposer → output`
> With `MemoryRetriever` feeding context into the builder.

---

## Intent Taxonomy

| Intent | Value | Trigger Pattern |
|--------|-------|----------------|
| GREETING | `"greeting"` | hello, hi, hey, good morning/afternoon/evening |
| FAREWELL | `"farewell"` | bye, goodbye, see you, good night |
| STATUS_QUERY | `"status_query"` | status, how are you, health, uptime |
| HELP_REQUEST | `"help_request"` | help, assist, how do/can/to |
| CODE_REQUEST | `"code_request"` | code, program, script, function, implement |
| EXPLAIN | `"explain"` | explain, what is, define, describe, how does |
| MEMORY_QUERY | `"memory_query"` | remember, recall, what did I say |
| SYSTEM_COMMAND | `"system_command"` | run, execute, check, scan |
| EMOTIONAL | `"emotional"` | sad, happy, angry, worried |
| OPINION | `"opinion"` | think, believe, prefer, opinion |
| FACTUAL | `"factual"` | what, when, where, how many |
| CREATIVE | `"creative"` | write, create, compose, imagine |
| SELF_REFLECT | `"self_reflect"` | who are you, what are you, introspect |
| UNKNOWN | `"unknown"` | fallback |

> [!warning] Bug #2 — `Intent.QUESTION` Does Not Exist
> AttributeError at runtime when LLM is available and memory results exist. Fixed — replaced with `Intent.EXPLAIN`. See [[Bug Fixes Registry#Bug 2]].

---

## IntentClassifier

Rule-based classifier with learning capability. Uses regex patterns per intent. Can learn new patterns from conversation feedback (Phase 3).

---

## Tool-Use Detection (`_detect_tool_intent`)

Asks LLM if message needs a code tool. Returns response string if tool used, `None` to proceed to normal chat.

- **Keyword pre-filter**: avoids unnecessary LLM calls for obvious non-tool messages
- **Decision loop**: runs through `self.llm.chat()` — swappable when [[HELENA-Net Model]] is ready
- **Direct reference** to `self._code_editor` for executing tool actions

---

## Chat Pipeline (`chat()` method)

```
1. _detect_tool_intent(message) → tool response or None
2. IntentClassifier.classify(message) → Intent
3. EmotionEngine.on_operator_interaction(sentiment) → update emotions
4. EmotionEngine.get_state() → snapshot for personality
5. memory.search(query) → relevant memories (non-GREETING/EXPLAIN only)
6. Build messages list:
   - System prompt (identity + self-knowledge + emotion + personality + memory)
   - History: self._history[-7:-1] (excludes current turn)
   - Current user message
7. llm.chat(messages) → response from Mistral
8. PersonalityEngine.apply() → modulate tone
9. ResponseFormatter.format() → final output
10. Store turn in self._history (ConversationTurn with .role, .text)
```

### Conversation History

- **Type**: `ConversationTurn` objects with `.role` and `.text` (NOT `.content` — Bug #7 in ARCHITECTURE.md)
- **Max**: 200 turns (`self._history`)
- **Window**: `self._history[-7:-1]` for Mistral context — excludes current turn which was already added at step 6

### System Prompt Structure

Built fresh each call:
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

[USER turn -6] ... [HELENA turn -5] ... (up to 6 history turns)
[USER: current message]
```

> [!warning] Bug #16 — Code Editor Can Be None (Crash)
> `hasattr(self, '_code_editor')` returns True even if `_code_editor` is None. Then `.root` crashes. Fix: check `self._code_editor is None` explicitly. See [[Bug Fixes Registry#Bug 16]].

---

## Security Alert Integration

AEGIS injects alerts via `inject_security_alert(message)` (from [[AEGIS/Integration Bridge]]):
- Adds message to `self._security_alerts` queue
- `get_pending_security_alerts()` picks up queued alerts at start of each response
- Prepends to system context so HELENA is aware before responding
- Queue capped at 10 messages

---

## Bug #29 — Typo "propperly"

System prompt contains misspelling `"propperly"` → should be `"properly"` on line 611. See [[Bug Fixes Registry#Bug 29]].

---

## Related Notes

- [[Kernel]] — ChatEngine constructed in kernel init after LLM
- [[Personality System]] — emotion/personality params injected into system prompt
- [[Memory System]] — `memory.search()` for context retrieval
- [[HELENA-Net Model]] — will replace LLM backend in HybridLLM
- [[AEGIS/Integration Bridge]] — inject_security_alert() method
