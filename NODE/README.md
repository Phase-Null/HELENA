---
tags: [meta, vault]
date: 2026-03-05
status: active
---

# NODE — HELENA Knowledge Organization Vault

**NODE** is HELENA's Obsidian vault for structured knowledge. It stores and organizes architecture documentation, AEGIS security documentation, training data specifications, and operational knowledge. It is part of HELENA's neural network — providing structured knowledge that can be referenced by the [[Kernel]], fed into [[Training Pipeline|training]], and used for operational debugging.

> [!info] What NODE Contains
> - **Architecture notes** — detailed documentation of every HELENA component, derived from actual source code
> - **AEGIS notes** — security system architecture, ETW providers, network agents, integration bridge
> - **Training notes** — dataset specs, synthetic data plans, model config presets
> - **Bug fixes registry** — comprehensive list of all 39 bugs with severity, affected files, and fix details
> - **Templates** — reusable note templates for documenting new components, bugs, and training data

## Vault Structure

```
NODE/
  .obsidian/          — Obsidian configuration (dark theme, Inter font)
  README.md           — This file (vault overview)
  Home.md             — Landing page / dashboard with wikilinks to all sections
  
  Architecture/       — HELENA core system documentation
    HELENA-Net Model.md      — SpikingSSM-MoE architecture (7 classes, config presets)
    Kernel.md                 — HELENAKernel central authority, init order, task lifecycle
    Personality System.md     — Emotion modulation, commentary, regulatory rules, Bug #10
    Memory System.md          — ChromaDB vector store, NetworkX graph, OfflineEmbedder
    Chat Engine.md            — ChatEngine, IntentClassifier, tool-use routing
    Runtime.md                — ResourceManager, GamingOptimizer, hardware profiles
    Training Pipeline.md      — AutonomousTrainer, dataset, evolution DB, safety governor
    Bug Fixes Registry.md     — All 39 bugs catalogued with severity and links
    Config Reference.md       — HelenaNetConfig defaults, YAML config, all settings
  
  AEGIS/              — Security core documentation
    Overview.md               — Rust-based security core, relationship to HELENA
    ETW System.md             — ETW providers, consumer callbacks, suspicious patterns
    Network Agent.md          — NetworkMonitor, path-validated safe process check
    State Management.md       — AegisState, ResponsePackage, VecDeque history
    Integration Bridge.md     — AEGIS ↔ HELENA bridge, security alerts, thread-safe lock
    Threat Model.md           — Three-layer language model, threat tiers, virtual defense
    Bug Fixes.md              — AEGIS-specific fixes (#4, #15, #22, #23, #24, #27, #33, #34)
  
  Training/           — ML training documentation
    HELENA-Net BASE.md        — BASE model config, Kaggle notebook, dataset analysis
    Dataset Analysis.md       — 2504 convs, 37.8% HELENA-voice, gaps, expansion plan
    Synthetic Data Plan.md    — Categories needed, generation approach, target volumes
    Prepare Dataset.md        — prepare_dataset.py, 5-source weighted hierarchy
  
  _templates/         — Reusable note templates
    Bug Fix Template.md       — Template for documenting bug fixes
    Component Template.md     — Template for documenting components
    Training Data Template.md — Template for training data specifications
```

## How to Use

1. **Start at [[Home]]** — the dashboard links to every section
2. **Navigate with wikilinks** — `[[Note Name]]` connects related content
3. **Use tags** — `#architecture`, `#aegis`, `#bugfix`, `#training` for filtering
4. **Read callouts** — `> [!info]`, `> [!warning]`, `> [!tip]` highlight key information
5. **Check backlinks** — Obsidian's graph view shows relationships between notes

## Key Decisions

- All content derived from **actual source code** — not generic placeholder text
- Bug fixes use the **official bug IDs** from HELENA_FULL_FIXES.md
- Cross-references connect Architecture ↔ AEGIS ↔ Training where dependencies exist
- Frontmatter metadata on key notes enables filtering and search
