// src/firewall/mod.rs
//
// AEGIS Firewall Layer — Phase 3 (v2, bug-fixed)
//
// Sub-modules:
//   engine.rs    — WFP session lifecycle, filter management
//   rules.rs     — IP blocking (netsh) + port blocking (WFP), rule metadata
//   responder.rs — Tier-based response decision logic (all 6 tiers implemented)
//
// Bug fixes in v2:
//   Bug 4:  Loopback permit restricted to 127.0.0.1 (IpAddressConditionBuilder)
//   Bug 23: Retaliate/Lockdown tiers now fully implemented
//   Bug 24: WFP filter IDs stored for proper removal
//   Bug 27: Only temporary IP blocks removed on shutdown
//   BUG-3:  Single-transaction loopback permit (no double commit)

pub mod engine;
pub mod rules;
pub mod responder;
pub mod ipc_auth;

pub use engine::FirewallEngine;
pub use responder::Responder;
pub use rules::{RuleSet, IPRuleMeta, summary, cleanup_temporary_rules, cleanup_all_rules};
