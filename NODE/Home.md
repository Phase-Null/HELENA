---
tags: [dashboard, home]
date: 2026-03-05
status: active
---

# 🏠 NODE — HELENA Knowledge Vault Dashboard

> [!quote] HELENA is not a chatbot. She is an AI system being built to evolve.
> — [[HELENA]]

Welcome to **NODE**, HELENA's knowledge organization system. This vault stores architecture documentation, security docs, training data specs, and operational knowledge — all derived from the actual source code.

---

## ⚡ Architecture

> [!info] Core System Components
> HELENA's architecture is a layered system: Kernel → Memory → Runtime → ML → Desktop

| Note | Key Content | Status |
|------|------------|--------|
| [[HELENA-Net Model]] | SpikingSSM-MoE: 7 classes, SSM+LIF+MoE, O(n) vs O(n²), ~15x compute reduction | `#architecture` `#ml` |
| [[Kernel]] | HELENAKernel — task queue, permission system, init order (LLM before ChatEngine) | `#architecture` `#kernel` |
| [[Personality System]] | Emotion modulation, Bug #10 (no-op fix), regulatory rules (8 ABS + 5 OPR + 3 ADV) | `#architecture` `#personality` |
| [[Memory System]] | ChromaDB + NetworkX, _OfflineEmbedder (384-dim BoW), threshold 0.6 | `#architecture` `#memory` |
| [[Chat Engine]] | IntentClassifier, _detect_tool_intent, 200-turn history, system prompt builder | `#architecture` `#chat` |
| [[Runtime]] | ResourceManager, GamingOptimizer, 85% CPU/RAM cap, hardware detection | `#architecture` `#runtime` |
| [[Training Pipeline]] | AutonomousTrainer, 6 stubs, evolution DB (SQLite), safety governor (stub) | `#architecture` `#training` |
| [[Bug Fixes Registry]] | **39 bugs**: 4 CRITICAL, 10 HIGH, 9 MEDIUM, 9 LOW, 3 re-audit, 1 phantom | `#bugfix` |
| [[Config Reference]] | HelenaNetConfig defaults, HELENA_NANO/BASE/LARGE presets, config.yaml | `#architecture` `#config` |

---

## 🔒 AEGIS — Security Core

> [!warning] AEGIS is HELENA's security nervous system
> Rust-based, kernel-level visibility, ETW monitoring, WFP firewall, 16 agents

| Note | Key Content | Status |
|------|------------|--------|
| [[Overview]] | Rust core, IPC port 47201, 16 Phase 1 agents, ETW + WFP + self-protection | `#aegis` |
| [[ETW System]] | 3 providers (Kernel-Process, DNS-Client, Security-Auditing), heartbeat monitor, suspicious patterns | `#aegis` `#etw` |
| [[Network Agent]] | NetworkMonitor v1-v4, path-validated `is_known_safe()`, suspicious ports, IP severity tracking | `#aegis` `#network` |
| [[State Management]] | AegisState, ResponsePackage, VecDeque history, 50-item pending cap, threat escalation | `#aegis` `#state` |
| [[Integration Bridge]] | AEGIS ↔ HELENA Python bridge, `inject_security_alert()`, `_get_security_lock()` (Bug #39) | `#aegis` `#integration` |
| [[Threat Model]] | 3-layer language model (Rust→Python→Kernel), 6 threat tiers, virtual defense architecture | `#aegis` `#threat` |
| [[Bug Fixes]] | AEGIS-specific: #4 loopback bypass, #15 regex→contains, #22 System per PID, #33 Vec→VecDeque | `#aegis` `#bugfix` |

---

## 🧠 Training

> [!tip] Training Pipeline
> HELENA-Net BASE targets <500ms CPU inference, ~50M active params, 4GB RAM minimum

| Note | Key Content | Status |
|------|------------|--------|
| [[HELENA-Net BASE]] | BASE config (512 d_model, 8 experts, 12 layers), Kaggle notebook, 334M total params | `#training` `#ml` |
| [[Dataset Analysis]] | 2504 conversations, 37.8% HELENA-voice, gaps in emotional/coding/security data | `#training` `#dataset` |
| [[Synthetic Data Plan]] | Categories needed: emotional, security, coding, architecture; target 10K convs | `#training` `#synthetic` |
| [[Prepare Dataset]] | 5-source weighted hierarchy, Helena 5x → OASST2 1x, prepare_dataset.py | `#training` `#dataset` |

---

## 🛠 Templates

| Template | Use Case |
|----------|----------|
| [[Bug Fix Template]] | Document new bug fixes with severity, file, description, fix code |
| [[Component Template]] | Document new components with purpose, architecture, dependencies, config |
| [[Training Data Template]] | Specify training data categories, conversation format, quality criteria |

---

## 🐛 Quick Links — Bug Fixes by Severity

> [!danger] CRITICAL Bugs (P0)
> [[Bug Fixes Registry#Bug 1]] — Trainer constructor missing `runtime` argument ✅ **Fixed**
> [[Bug Fixes Registry#Bug 2]] — `Intent.QUESTION` does not exist ✅ **Fixed**
> [[Bug Fixes Registry#Bug 3]] — `validation_result.errors` should be `.issues` ✅ **Fixed**
> [[Bug Fixes Registry#Bug 4]] — AEGIS Firewall loopback permit allows ALL traffic ✅ **Fixed**

> [!warning] HIGH Bugs (P1) — Needs Fix
> [[Bug Fixes Registry#Bug 5]] — `wipe_memory` dead code
> [[Bug Fixes Registry#Bug 7]] — train.py double-counted loss
> [[Bug Fixes Registry#Bug 8]] — `--config large` silently falls back to NANO
> [[Bug Fixes Registry#Bug 9]] — Encryption key lost on restart
> [[Bug Fixes Registry#Bug 10]] — Emotion modulation is a no-op (3 sub-bugs)
> [[Bug Fixes Registry#Bug 13]] — MoE routing uses wrong probabilities
> [[Bug Fixes Registry#Bug 14]] — ChaCha20 without authentication
> [[Bug Fixes Registry#Bug 15]] — Regex pattern used with contains()
> [[Bug Fixes Registry#Bug 16]] — Code editor can be None (crash)
