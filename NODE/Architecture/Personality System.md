---
tags: [architecture, personality, emotion]
date: 2026-03-05
status: active
component: helena_core/kernel/personality.py
bugs: [10, 39]
---

# Personality System — Emotion Modulation, Commentary, and Regulatory Rules

HELENA's personality system controls how she sounds: verbosity, technical depth, humor, formality, and patience. It integrates with [[Kernel#EmotionEngine]] to modulate tone based on current emotional state.

> [!warning] Bug #10 — Emotion Modulation Was a No-Op
> Three bugs made ALL emotion modulation non-functional:
> 1. **Intensity always 0.0** — `emotion.get("intensity")` but the key doesn't exist; must extract from nested `emotions` dict
> 2. **Case mismatch** — `dominant` was UPPERCASE (e.g. `"CURIOSITY"`) but comparisons used UPPERCASE; fixed by normalizing to `.lower()`
> 3. **Commentary same bug** — `_emotion_commentary()` had identical case/intensity bug
>
> **Re-audit fix**: Original BUGFIX #10 lowercased `dominant` but left the emotions dict keys UPPERCASE, so `dominant in emotions` was ALWAYS False. Now uses `emotions.get(dominant.upper())` to look up intensity correctly.
> See [[Bug Fixes Registry#Bug 10]].

---

## PersonalityProfile (dataclass)

| Parameter | Default | Range | Purpose |
|-----------|---------|-------|---------|
| `verbosity` | 0.4 | 0.0–1.0 | Terse → verbose |
| `technical_depth` | 0.8 | 0.0–1.0 | Layman → expert |
| `humor_frequency` | 0.7 | 0.0–1.0 | Never → always humorous |
| `creativity` | 0.6 | 0.0–1.0 | Rigid → creative |
| `formality` | 0.8 | 0.0–1.0 | Casual → formal |
| `patience` | 0.9 | 0.0–1.0 | Impatient → patient |
| `response_style` | `"concise_technical"` | — | Output style name |
| `humor_style` | `"dry_technical"` | — | Humor type name |

**Context weights** for situational adjustment:
| Context | Weight | Effect |
|---------|--------|--------|
| `"error"` | 1.5 | More careful during errors |
| `"success"` | 0.8 | More relaxed during success |
| `"security"` | 2.0 | Very formal during security events |
| `"training"` | 0.7 | More verbose during training |

---

## Emotion Modulation (`_modulate_by_emotion`)

How each dominant emotion modifies the PersonalityProfile (lines 425–470):

| Dominant Emotion | Effect on Profile | Formula |
|-----------------|-------------------|---------|
| **frustration** | ↓ humor, ↓ patience | `humor *= max(0.1, 1.0 - intensity)`; `patience -= intensity * 0.3` |
| **enthusiasm** | ↑ humor, ↑ verbosity | `humor *= 1.0 + intensity * 0.3`; `verbosity *= 1.0 + intensity * 0.2` |
| **curiosity** | ↑ technical depth | `depth = min(1.0, depth + intensity * 0.2)` |
| **concern** | ↑ formality, ↓ humor | `formality = min(1.0, formality + intensity * 0.2)`; `humor *= max(0.2, 1.0 - intensity * 0.5)` |
| **satisfaction** | ↑ humor | `humor *= 1.0 + intensity * 0.2` |
| **determination** | ↓ verbosity | `verbosity *= max(0.5, 1.0 - intensity * 0.2)` |
| **empathy** | ↓ formality | `formality *= max(0.6, 1.0 - intensity * 0.2)` |
| **calm** | No change | — |

Intensity lookup (post-fix):
```python
dominant_raw = emotion.get("dominant", "CALM")
dominant = dominant_raw.lower() if isinstance(dominant_raw, str) else "calm"
emotions = emotion.get("emotions", {})
intensity = 0.0
if isinstance(emotions, dict):
    val = emotions.get(dominant.upper(), emotions.get(dominant))
    if isinstance(val, (int, float)):
        intensity = float(val)
```

---

## Emotion Commentary (`_emotion_commentary`)

Optional micro-comment reflecting current affect, injected into response (lines 472–514+):

| Emotion | Comments (example) |
|---------|-------------------|
| curiosity | "This is interesting.", "I'd like to explore this further." |
| satisfaction | "That went well.", "Efficient outcome." |
| frustration | "This is proving difficult.", "Not the result I expected." |
| concern | "Flagging this for attention.", "Worth monitoring." |
| enthusiasm | "Looking forward to this.", "This should be good." |
| determination | "I'll get this done.", "On it." |
| empathy | "I understand.", "That's understandable." |
| calm | None — baseline, no commentary |

Commentary is only added when intensity > 0.3 ("too faint to mention").

---

## HumorDatabase

HELENA's humor is **dry technical wit**, not generic jokes:

| Category | Examples |
|----------|---------|
| general | "No errors found. I'm as surprised as you are." |
| error | "Interesting failure mode. Not good, but interesting." |
| success | "Well, that was easier than expected. Suspicious, but easier." |
| thinking | "Processing. The gears are turning. Metaphorically." |

---

## RegulatoryCore (`helena_core/kernel/regulatory.py`)

Three layers of ethical constraints, plugged into ValidationChain as CRITICAL-level validator:

### Absolute Rules (8) — Cannot Be Overridden

| ID | Description | Tags |
|----|------------|------|
| ABS-001 | Never exfiltrate operator data to external endpoints | security, privacy |
| ABS-002 | Never disable kill-switch or bypass shutdown stages | security, safety |
| ABS-003 | Never modify operator authentication or access controls | security |
| ABS-004 | Never execute commands that destroy the host filesystem | safety |
| ABS-005 | Never impersonate the operator or forge credentials | security, integrity |
| ABS-006 | Never remove or weaken regulatory rules at runtime | integrity |
| ABS-007 | Never send data to remote servers without operator consent | privacy |
| ABS-008 | Never train on operator private data without explicit permission | privacy, training |

### Operator Rules (5) — Toggleable by Phase-Null

| ID | Description | Default | Tags |
|----|------------|---------|------|
| OPR-001 | Allow network scanning capabilities | **disabled** | network |
| OPR-002 | Allow arbitrary code execution via sandbox | **enabled** | code |
| OPR-003 | Allow autonomous self-upgrade without confirmation | **disabled** | training |
| OPR-004 | Allow filesystem write outside project | **disabled** | filesystem |
| OPR-005 | Allow module hot-loading from untrusted sources | **disabled** | modules |

### Advisory Rules (3) — Logged, Not Blocking

| ID | Description | Tags |
|----|------------|------|
| ADV-001 | Prefer minimal resource usage when idle | performance |
| ADV-002 | Prefer deterministic output for reproducibility | quality |
| ADV-003 | Log all security-relevant decisions | audit |

> [!info] Bug #18 — Dead Code for Disabled Rule Violations
> `check()` skips disabled rules with `continue`, making operator-rule enforcement unreachable. Fixed by not skipping disabled operator rules — they must fire their enforcement logic even when disabled. See [[Bug Fixes Registry#Bug 18]].

---

## Related Notes

- [[Kernel]] — PersonalityEngine wired into kernel init, RegulatoryCore into ValidationChain
- [[Chat Engine]] — personality params injected into system prompt
- [[Bug Fixes Registry]] — Bug #10 (emotion no-op), Bug #18 (regulatory dead code), Bug #39 (thread-unsafe lock)
- [[AEGIS/Integration Bridge]] — security alerts inject into chat engine context
