---
tags: [architecture, config]
date: 2026-03-05
status: active
---

# Config Reference — HelenaNetConfig and YAML Settings

Complete reference for all configuration options, from model architecture defaults to runtime YAML settings.

---

## HelenaNetConfig (`helena_ml/helena_llm/config.py`)

Full dataclass with all fields and defaults:

### Vocabulary

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `vocab_size` | `int` | 8192 | Small vocab = fast embedding lookup |
| `pad_token_id` | `int` | 0 | Padding token |
| `bos_token_id` | `int` | 1 | Beginning of sequence |
| `eos_token_id` | `int` | 2 | End of sequence |
| `unk_token_id` | `int` | 3 | Unknown token |

### Model Dimensions

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `d_model` | `int` | 512 | Core hidden dimension |
| `d_state` | `int` | 64 | SSM state dimension ("the memory") |
| `d_conv` | `int` | 4 | Local convolution width in SSM |
| `d_inner` | `int` | 1024 | Expanded inner dimension (SSM) |
| `n_layers` | `int` | 12 | Number of SpikingSSM-MoE blocks |

### Spiking Neuron Parameters (LIF)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `lif_threshold` | `float` | 0.5 | Membrane potential threshold to fire |
| `lif_leak` | `float` | 0.9 | Membrane decay factor (β) |
| `lif_reset` | `float` | 0.0 | Reset potential after firing |
| `surrogate_slope` | `float` | 25.0 | Slope for surrogate gradient (training) |

### Mixture of Experts

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `n_experts` | `int` | 8 | Total expert networks |
| `n_experts_active` | `int` | 2 | Experts activated per token |
| `expert_capacity_factor` | `float` | 1.25 | Load balancing headroom |
| `d_expert` | `int` | 2048 | Expert FFN hidden dimension |

### Training

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `max_seq_len` | `int` | 256 | Maximum sequence length |
| `dropout` | `float` | 0.1 | Dropout rate |
| `learning_rate` | `float` | 3e-4 | Optimizer learning rate |
| `weight_decay` | `float` | 0.01 | Weight decay |
| `warmup_steps` | `int` | 5 | LR warmup |
| `max_steps` | `int` | 100 | Total training steps |
| `batch_size` | `int` | 8 | Training batch size |
| `grad_clip` | `float` | 1.0 | Gradient clipping max norm |

### Inference

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `temperature` | `float` | 0.7 | Sampling temperature |
| `top_p` | `float` | 0.9 | Nucleus sampling threshold |
| `top_k` | `int` | 50 | Top-K sampling |
| `max_new_tokens` | `int` | 512 | Maximum generated tokens |
| `repetition_penalty` | `float` | 1.1 | Repetition penalty factor |

### Paths

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `save_path` | `str` | `./helena_memory/helena_net` | Model save directory |
| `conversation_data_path` | `str` | `./helena_memory/conversations.jsonl` | Training data path |

### Computed Properties

| Property | Formula | BASE Result |
|----------|---------|-------------|
| `total_params_estimate` | `embed + n_layers × (ssm_per_layer + moe_per_layer)` | "Total: ~334M params | Active per token: ~50M params" |

---

## Config Presets

```python
HELENA_NANO = HelenaNetConfig(
    d_model=256, d_state=32, d_inner=512, n_layers=6,
    n_experts=4, n_experts_active=1, d_expert=1024,
    vocab_size=8192, max_seq_len=256,
)   # ~28M total, ~10M active

HELENA_BASE = HelenaNetConfig()  # defaults above — ~334M total, ~50M active

HELENA_LARGE = HelenaNetConfig(
    d_model=1024, d_state=128, d_inner=2048, n_layers=24,
    n_experts=16, n_experts_active=2, d_expert=4096,
    vocab_size=16384, max_seq_len=4096,
)   # ~2.1B total, ~200M active
```

> [!warning] Bug #8 — `--config large` Silently Falls Back to NANO
> HELENA_LARGE exists in config.py but is NOT imported in train.py, and NOT in config_map. The `--config large` flag silently uses NANO instead. See [[Bug Fixes Registry#Bug 8]].

---

## YAML Configuration (`config.default.yaml`)

### Operator

```yaml
operator:
  name: "Operator"
  security_level: "admin"
```

### Kernel

```yaml
kernel:
  default_mode: "ENGINEERING"
  max_concurrent_tasks: 8
  task_timeout_seconds: 300
  enable_background_mode: true
```

### Runtime

```yaml
runtime:
  cpu_limit_percent: 80
  ram_limit_mb: 4096
  gpu_enabled: false
  gaming_compat: true
  power_profile: "balanced"    # balanced | performance | efficiency
```

### Memory

```yaml
memory:
  vector_dimension: 384         # Must match OfflineEmbedder (Bug #19)
  max_entries: 100000
  persistence_dir: "data/memory"
  graph_file: "data/memory/graph.json"
```

### Chat

```yaml
chat:
  max_history: 200              # ConversationTurn limit
  response_max_length: 2000
  enable_memory_integration: true
  enable_emotion_integration: true
```

### Emotion

```yaml
emotion:
  enabled: true
  decay_interval_seconds: 60
  max_events: 1000
```

### Personality

```yaml
personality:
  verbosity: 0.4
  technical_depth: 0.8
  humor_threshold: 0.7
  creativity_level: 0.6
  formality_level: 0.8
  response_style: "concise_technical"
```

### Training

```yaml
training:
  enabled: true
  schedule_interval: 3600       # seconds between auto-training cycles
  min_cooldown: 600
  daily_time: "02:00"
  weekly_day: "sunday"
  weekly_time: "03:00"
  idle_minutes: 30
  max_duration_hours: 2
```

### Security

```yaml
security:
  kill_switch_enabled: true
  regulatory_core_enabled: true
  allow_network_scan: false
  allow_code_execution: true
  allow_autonomous_upgrade: false
```

---

## Related Notes

- [[HELENA-Net Model]] — architecture classes using these configs
- [[Kernel]] — runtime config consumed by HELENAKernel
- [[Runtime]] — hardware profiles and resource limits
- [[Bug Fixes Registry]] — Bug #8 (large config), Bug #19 (dimension mismatch)
