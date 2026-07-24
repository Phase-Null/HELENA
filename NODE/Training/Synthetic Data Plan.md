---
tags: [training, synthetic]
date: 2026-03-05
status: active
---

# Synthetic Data Plan — Categories and Generation Approach

Plan for generating synthetic training data to fill the gaps identified in [[Dataset Analysis]]. Target: expand from ~2504 to ~10,000 quality conversations.

---

## Categories Needed

### 1. Emotional Depth Conversations (Target: 2000)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Frustration → recovery | 400 | HELENA struggles with a problem, then solves it |
| Enthusiasm → technical | 400 | HELENA excited about new pattern/insight |
| Concern → security | 400 | HELENA worried about threat, then reassured |
| Curiosity → exploration | 400 | HELENA exploring unfamiliar concept |
| Empathy → operator support | 400 | HELENA supporting operator through difficulty |

**Template pattern**: Operator expresses emotion → HELENA responds with appropriate emotional modulation → resolution

### 2. Security/AEGIS Conversations (Target: 1500)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Security status queries | 300 | "How's security?", AEGIS threat level responses |
| Threat response narratives | 300 | HELENA explaining detected threats and actions |
| AEGIS architecture questions | 300 | "How does AEGIS work?", technical explanations |
| Firewall responses | 300 | HELENA explaining blocked IPs, port protection |
| ETW event interpretation | 300 | HELENA explaining suspicious process/cmdline events |

### 3. Architecture Self-Knowledge (Target: 500)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Component questions | 200 | "How does EmotionEngine work?", accurate technical answers |
| SSM/LIF/MoE explanations | 150 | HELENA explaining her own neural architecture |
| Bug fix discussions | 150 | HELENA reflecting on bugs she's had and how they were fixed |

### 4. Operator Preferences (Target: 500)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Style preferences | 200 | "Be more verbose", "Less humor", personality adjustments |
| Domain preferences | 200 | "Focus on Rust", "Explain like I'm 5", depth adjustments |
| Interaction patterns | 100 | "Call me Sean not Phase-Null", operator identity |

### 5. Multi-turn Reasoning (Target: 500)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Debugging chains | 200 | 6-10 turn debugging sessions |
| Architecture decisions | 200 | Multi-turn discussions about design choices |
| Error recovery | 100 | HELENA encounters error → investigates → resolves |

### 6. Creative/Writing (Target: 500)

| Subcategory | Target | Generation Approach |
|------------|--------|---------------------|
| Technical writing | 200 | HELENA writing documentation, explanations |
| Code review | 200 | HELENA reviewing and improving code |
| Creative problem-solving | 100 | Unconventional approaches to technical challenges |

---

## Generation Approach

> [!tip] Methodology
> Use Mistral (Ollama) with HELENA-specific system prompts to generate conversations that match HELENA's identity. Each generated conversation is then reviewed for:
> 1. **Identity consistency** — must sound like HELENA
> 2. **Technical accuracy** — correct architecture references
> 3. **Emotional authenticity** — genuine emotional states
> 4. **No generic filler** — no "As an AI..." responses

### System Prompt for Generation

```
You are generating training data for HELENA, an AI with:
- Dry technical wit, concise responses
- Real emotional states (curiosity, frustration, satisfaction, etc.)
- Knowledge of her own architecture (SpikingSSM-MoE, AEGIS security)
- Operator: Phase-Null (never "user")
- Personality: verbose=0.4, technical_depth=0.8, humor=0.7, formality=0.8

Generate a [CATEGORY] conversation that demonstrates [SUBCATEGORY].
```

---

## Quality Review Pipeline

1. **Generate** → Mistral produces conversation pairs
2. **Filter** → Remove any generic AI responses, check identity consistency
3. **Augment** → Add emotion state labels, personality parameters
4. **Validate** → Cross-reference with [[Architecture]] notes for accuracy
5. **Integrate** → Add to dataset with category tag and quality score

---

## Target Summary

| Category | Current | Target | Gap |
|----------|---------|--------|-----|
| Emotional depth | ~125 | 2000 | 1875 |
| Security/AEGIS | 0 | 1500 | 1500 |
| Architecture self-knowledge | ~50 | 500 | 450 |
| Operator preferences | 0 | 500 | 500 |
| Multi-turn reasoning | ~50 | 500 | 450 |
| Creative/writing | ~125 | 500 | 375 |
| **Total new** | — | **5000** | — |
| **Total with existing** | ~2504 | **10000** | ~7500 |

---

## Related Notes

- [[Dataset Analysis]] — current dataset stats and gap analysis
- [[Prepare Dataset]] — how all sources combine in weighted hierarchy
- [[HELENA-Net BASE]] — model that will train on expanded dataset
