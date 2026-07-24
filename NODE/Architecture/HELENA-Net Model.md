---
tags: [architecture, ml, helena-net]
date: 2026-03-05
status: active
component: helena_ml/helena_llm/architecture.py
config: helena_ml/helena_llm/config.py
---

# HELENA-Net Model — SpikingSSM-MoE Architecture

HELENA's own language model. A novel architecture combining three ideas for fast local CPU inference, replacing Mistral in [[Kernel|HybridLLM]] when trained (Phase 4).

> [!tip] Design Targets
> - **<500ms** response on CPU (no GPU required)
> - **~50M** active parameters per forward pass (MoE keeps this low)
> - Runs on **4GB RAM** minimum
> - Trained on HELENA's own conversation history
> - **~15x** less compute than equivalent dense transformer

---

## Architecture Overview

```
Token → Embedding → [+ Positional Bias] → Dropout →
  ┌─ SpikingSSMMoEBlock × 12 ─────────────────────┐
  │   1. SSMLayer  — O(n) temporal mixing          │
  │   2. LIFNeuron — sparsify (~85% outputs = 0)   │
  │   3. SparseMoE — 8 experts, top-2 activated    │
  └─────────────────────────────────────────────────┘
→ RMSNorm → LM Head (weight-tied with embedding) → logits
```

Combined effect:
- **SSM**: O(n) sequence processing instead of O(n²) attention
- **LIF**: ~85% of neuron outputs are zero → massive compute reduction
- **MoE**: only 25% of expert parameters activate per token
- **Net result**: ~15x less compute than an equivalent dense transformer

---

## Class Inventory (7 Classes)

### 1. `SurrogateSpike` — `torch.autograd.Function` (lines 62–86)

Surrogate gradient for spike function. Solves the fundamental problem that the real gradient of a step function is zero almost everywhere (breaks backprop).

| Method | Purpose |
|--------|---------|
| `forward(ctx, membrane, threshold, slope)` | Returns `(membrane >= threshold).float()` — binary spike |
| `backward(ctx, grad_output)` | Returns `grad_output * surrogate` where `surrogate = slope * sigmoid(x) * (1 - sigmoid(x))` |

- `ctx.save_for_backward(membrane)` preserves membrane potential for gradient computation
- `slope = 25.0` by default — controls smoothness of approximation

### 2. `LIFNeuron` — `nn.Module` (lines 89–131)

Leaky Integrate-and-Fire neuron layer. The sparsification engine.

**Membrane dynamics:**
```
V(t) = β * V(t-1) + I(t)          [integrate with leak]
spike(t) = 1 if V(t) >= θ else 0  [fire if above threshold]
V(t) = V(t) - spike(t) * θ        [soft reset after firing]
```

| Parameter | Config Key | Default | Purpose |
|-----------|-----------|---------|---------|
| `self.threshold` | `lif_threshold` | 0.5 | Membrane potential threshold to fire |
| `self.leak` | `lif_leak` | 0.9 | Membrane decay factor (β) |
| `self.slope` | `surrogate_slope` | 25.0 | Surrogate gradient slope |

**`forward(current, membrane)`** signature:
- `current`: `[batch, seq, d_model]` — input current
- `membrane`: previous membrane potential (None = start fresh)
- Returns: `(spikes: [batch, seq, d_model], membrane: [batch, d_model])`

Implementation: sequential loop over time steps, updating membrane and calling `SurrogateSpike.apply()` per step.

### 3. `SSMLayer` — `nn.Module` (lines 136–268)

Simplified Structured State Space Model layer. Based on S4/Mamba family.

**State update (per position):**
```
h(t) = A ⊙ h(t-1) + B(t) ⊙ x(t)
y(t) = C(t) · h(t) + D ⊙ x(t)
```

| Sub-component | Dimensions | Purpose |
|---------------|-----------|---------|
| `in_proj` | `d → d_inner*2` | Dual branch: x for SSM, z for gating |
| `conv1d` | `d_inner → d_inner`, kernel `d_conv=4` | Local convolution (short-range) |
| `A_log` | `[d_inner, d_state]` | Diagonal state decay (log(-A) for stability) |
| `D` | `[d_inner]` | Skip connection scalar |
| `x_proj` | `d_inner → d_state*2 + 1` | Input-dependent dt, B, C (selectivity) |
| `dt_proj` | `1 → d_inner` | Step size projection |
| `out_proj` | `d_inner → d` | Output projection |

> [!warning] Memory Fix (v2)
> Original code precomputed `dA = exp(dt ⊗ A)` as full `[B,L,d_inner,d_state]` tensor — ~134MB fp16 per layer, ~3.2GB for all 12 layers' autograd storage.
> 
> **Fix 1**: Per-step `dA_t` and `dB_t` computed inside scan loop. Peak memory: O(d_inner × d_state) per layer instead of O(L × d_inner × d_state).
> 
> **Fix 2**: Gradient checkpointing via `model.enable_gradient_checkpointing()`. Halves activation memory at ~33% slower backward.

**SSM scan loop** (lines 244–258):
```python
for t in range(seq):
    dt_t = dt[:, t, :]                                    # [B, d_inner]
    B_t  = B[:, t, :]                                     # [B, d_state]
    dA_t = torch.exp(dt_t.unsqueeze(-1) * A_neg.unsqueeze(0))  # per-step
    dB_t = dt_t.unsqueeze(-1) * B_t.unsqueeze(1)               # per-step
    h   = dA_t * h + dB_t * x_conv[:, t, :].unsqueeze(-1)
    y_t = (h * C[:, t, :].unsqueeze(1)).sum(dim=-1)
```

### 4. `Expert` — `nn.Module` (lines 273–283)

Single expert FFN network. SiLU-gated SwiGLU variant:
```python
self.gate_proj = nn.Linear(d_model, d_expert, bias=False)
self.up_proj   = nn.Linear(d_model, d_expert, bias=False)
self.down_proj = nn.Linear(d_expert, d_model, bias=False)
# forward: down_proj(SiLU(gate_proj(x)) * up_proj(x))
```

### 5. `SparseMoELayer` — `nn.Module` (lines 286–338)

Sparse Mixture of Experts layer. Router selects top-k experts per token.

| Attribute | Value | Purpose |
|-----------|-------|---------|
| `n_experts` | 8 | Total expert networks |
| `n_active` | 2 | Experts activated per token |
| `router` | `nn.Linear(d_model, n_experts)` | Learned router |
| `_aux_loss` | MSE between expert usage and uniform | Prevents expert collapse |

> [!warning] Bug #13 — MoE Routing Uses Wrong Probabilities
> Expert outputs weighted by `router_probs` (full softmax) instead of `top_k_probs` (renormalized). Weights don't sum to 1.0 per token. See [[Bug Fixes Registry#Bug 13]].

**Dispatch logic** (lines 325–332):
```python
for expert_idx in range(self.n_experts):
    mask = (top_k_indices == expert_idx).any(dim=-1)
    tokens = x_flat[mask]
    expert_out = self.experts[expert_idx](tokens)
    weights = router_probs[mask, expert_idx].unsqueeze(-1)  # BUG: should be top_k_probs
    output[mask] += weights * expert_out
```

### 6. `SpikingSSMMoEBlock` — `nn.Module` (lines 343–388)

One full block. Processing order:
1. **SSM layer** — temporal mixing (captures patterns across sequence)
2. **LIF spiking layer** — sparsification (reduce active neurons ~85%)
3. **MoE FFN layer** — feature mixing (expert knowledge routing)

Additional components:
- `lif_proj_in`: `nn.Linear(d_model, d_model)` — project into LIF
- `lif_proj_out`: `nn.Linear(d_model, d_model)` — project spikes back
- `norm_lif`: RMSNorm before LIF projection

**`forward(x, membrane)`** — returns `(transformed_x, updated_membrane)`

### 7. `HelenaNet` — `nn.Module` (lines 392–535)

The full model. Combines all blocks with embedding and output head.

| Component | Details |
|-----------|---------|
| `embedding` | `nn.Embedding(vocab_size, d_model, padding_idx=0)` |
| `pos_bias` | `nn.Parameter([1, max_seq_len, d_model])` — learned positional bias |
| `blocks` | `nn.ModuleList([SpikingSSMMoEBlock × n_layers])` |
| `norm_out` | RMSNorm |
| `lm_head` | `nn.Linear(d_model, vocab_size)` — **weight-tied** with embedding |
| `dropout` | `nn.Dropout(0.1)` |

**`forward(input_ids, targets, membranes)`** returns `(logits, loss, membranes)`:
- Loss = `F.cross_entropy(logits, targets, ignore_index=pad_token_id)` + `0.01 * aux_loss`
- Gradient checkpointing: `checkpoint(make_block_fn(block), x, use_reentrant=False)` when `self.gradient_checkpointing and self.training`

**`enable_gradient_checkpointing()`** — halves activation memory, ~33% slower backward.

---

## Config Presets

| Preset | d_model | d_state | d_inner | n_layers | n_experts | n_active | d_expert | vocab | max_seq | Total Params |
|--------|---------|---------|---------|----------|-----------|----------|----------|-------|---------|-------------|
| **HELENA_NANO** | 256 | 32 | 512 | 6 | 4 | 1 | 1024 | 8192 | 256 | ~28M |
| **HELENA_BASE** | 512 | 64 | 1024 | 12 | 8 | 2 | 2048 | 8192 | 256 | ~334M |
| **HELENA_LARGE** | 1024 | 128 | 2048 | 24 | 16 | 2 | 4096 | 16384 | 4096 | ~2.1B |

> [!info] BASE Active Parameters
> ~50M active params per token (only 2 of 8 experts fire). Total ~334M but inference cost similar to a ~50M dense model.

See [[Config Reference]] for full HelenaNetConfig field listing.
