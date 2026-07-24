---
tags: [training, ml]
date: 2026-03-05
status: active
---

# HELENA-Net BASE — Model Configuration and Training Setup

BASE is the default HELENA-Net configuration — designed to be the first model HELENA trains for herself. It targets <500ms CPU inference, ~50M active params per token, and 4GB RAM minimum.

---

## BASE Configuration (Defaults)

```python
HELENA_BASE = HelenaNetConfig()  # Uses all defaults

# Key dimensions:
d_model=512, d_state=64, d_inner=1024, n_layers=12
n_experts=8, n_experts_active=2, d_expert=2048
vocab_size=8192, max_seq_len=256

# Parameter estimate:
# Total: ~334M params | Active per token: ~50M params
```

---

## Training Parameters (BASE Defaults)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `max_seq_len` | 256 | Maximum input sequence length |
| `dropout` | 0.1 | Regularization |
| `learning_rate` | 3e-4 | Adam optimizer LR |
| `weight_decay` | 0.01 | L2 regularization |
| `warmup_steps` | 5 | LR warmup |
| `max_steps` | 100 | Total training steps |
| `batch_size` | 8 | Per-batch samples |
| `grad_clip` | 1.0 | Gradient clipping |

---

## Inference Parameters (BASE Defaults)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `temperature` | 0.7 | Sampling temperature |
| `top_p` | 0.9 | Nucleus sampling |
| `top_k` | 50 | Top-K sampling |
| `max_new_tokens` | 512 | Maximum generated tokens |
| `repetition_penalty` | 1.1 | Prevent repetition |

---

## Memory Efficiency (v2 Fixes)

> [!warning] Without these fixes, BASE OOMs on first step
> 
> **Fix 1 — Per-step dA/dB**: Compute discretized A and B one timestep at a time inside the SSM scan loop. Peak memory: O(d_inner × d_state) per layer instead of O(L × d_inner × d_state).
> 
> **Fix 2 — Gradient checkpointing**: Optional recomputation of block activations during backward pass. Halves activation memory at ~33% slower backward. Enable via `model.enable_gradient_checkpointing()`.
> 
> Together, these allow BASE (334M params) to train on a single T4 (15GB) with batch_size=4 and mixed precision.

---

## Training Script (`helena_ml/helena_llm/train.py`)

> [!warning] Bug #7 — Double-Counted Loss
> `total_loss` accumulated twice per step — line 357 `total_loss += loss.item()` is duplicate of line 363 `total_loss += step_loss`. Average loss reported is ~2x actual. Fix: delete line 357. See [[Bug Fixes Registry#Bug 7]].

> [!warning] Bug #8 — `--config large` Falls Back to NANO
> HELENA_LARGE not imported in train.py (line 29) and not in config_map (line 412). Fix: add to import and config_map. See [[Bug Fixes Registry#Bug 8]].

---

## Kaggle Notebook

Training runs on Kaggle (free T4 GPU). The notebook:
1. Installs dependencies (torch, ferrisetw for AEGIS test)
2. Clones HELENA repo
3. Runs `prepare_dataset.py` to combine sources
4. Trains HELENA-Net BASE with mixed precision
5. Saves model to `./helena_memory/helena_net`

---

## Related Notes

- [[HELENA-Net Model]] — full architecture documentation
- [[Dataset Analysis]] — current dataset stats and gaps
- [[Prepare Dataset]] — 5-source weighted hierarchy
- [[Config Reference]] — full config listing with defaults
- [[Bug Fixes Registry]] — Bug #7 (double loss), Bug #8 (large config)
