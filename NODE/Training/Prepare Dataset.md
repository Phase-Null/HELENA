---
tags: [training, dataset]
date: 2026-03-05
status: active
component: prepare_dataset.py
---

# Prepare Dataset — 5-Source Weighted Hierarchy

`prepare_dataset.py` combines all training sources into a single weighted JSONL file. This is run locally before uploading to Kaggle, or as a Kaggle cell. Output: `helena_base_dataset.jsonl`.

---

## Data Hierarchy (Most Important First)

| Priority | Source | Repeat Weight | Purpose |
|----------|--------|--------------|---------|
| 1 | Helena conversations | **5x** | Real, highest weight — authentic HELENA voice |
| 2 | Hand-crafted conversations | **5x** | Identity-critical, high weight |
| 3 | Architecture knowledge | **3x** | Paper content in HELENA's voice |
| 4 | Python coding conversations | **2x** | HELENA's actual domain |
| 5 | OASST2 | **1x** (capped at 1000) | Language breadth, small ratio |

> [!tip] Why Repeat Rather Than Just Add More Data
> Repetition signals importance. The model sees HELENA-specific content more often, so those patterns get reinforced more strongly per step. This compensates for having fewer HELENA conversations than OASST2 entries.

---

## Configuration Constants

```python
HELENA_CONVS_PATH   = "helena_memory/conversations.jsonl"
OUTPUT_PATH         = "helena_base_dataset.jsonl"
OASST2_MAX          = 1000

HELENA_REPEAT       = 5
HANDCRAFTED_REPEAT  = 5
ARCHITECTURE_REPEAT = 3
CODING_REPEAT       = 2
OASST2_REPEAT       = 1
```

---

## Pipeline Steps

### 1. Load JSONL Sources

```python
def load_jsonl(path):
    """Load conversations from a JSONL file."""
    convs = []
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found, skipping.")
        return convs
    with open(path, 'r') as f:
        for line in f:
            conv = json.loads(line)
            convs.append(conv)
    return convs
```

### 2. Load OASST2 (special handling)

OASST2 requires filtering for English conversations and quality. Capped at 1000 entries to prevent overwhelming HELENA-voice content.

### 3. Load Hand-crafted Conversations

Manually written conversations that capture HELENA's identity markers:
- Operator name references (Phase-Null)
- Personality quirks (dry humor, concise technical)
- Architecture self-knowledge
- Emotional honesty

### 4. Load Architecture Knowledge

Convert the SpikingSSM-MoE paper content into HELENA-voice conversations. HELENA explaining her own architecture to Phase-Null.

### 5. Apply Repetition Weights

```python
def apply_weights(conversations, repeat_count):
    """Repeat conversations to signal importance."""
    return conversations * repeat_count
```

### 6. Shuffle and Combine

All weighted sources shuffled together to prevent sequential bias:

```python
all_conversations = (
    helena_weighted + handcrafted_weighted +
    architecture_weighted + coding_weighted +
    oasst2_weighted
)
random.shuffle(all_conversations)
```

### 7. Write Output JSONL

```python
with open(OUTPUT_PATH, 'w') as f:
    for conv in all_conversations:
        f.write(json.dumps(conv) + '\n')
```

---

## Expected Output Size

| Source | Raw Count | Weighted Count |
|--------|-----------|---------------|
| Helena conversations | ~946 | ~4730 |
| Hand-crafted | ~100 | ~500 |
| Architecture knowledge | ~50 | ~150 |
| Python coding | ~500 | ~1000 |
| OASST2 (capped) | ~1000 | ~1000 |
| **Total** | ~2596 | **~7380** |

With [[Synthetic Data Plan]] additions (5000 new convs), total would reach ~12,380 before weighting.

---

## Related Notes

- [[HELENA-Net BASE]] — model trained on this dataset
- [[Dataset Analysis]] — current dataset stats and gaps
- [[Synthetic Data Plan]] — planned expansion categories
