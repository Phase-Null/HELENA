// src/firewall/mod.rs
//
// Phase 3 — WFP firewall layer.
//
// Three sub-modules:
//   engine.rs   — WFP session lifecycle. Opens the engine, registers HELENA's
//                 provider and sublayer, closes cleanly on drop.
//   rules.rs    — The actual firewall operations: block_ip, unblock_ip,
//                 block_port, list_active_rules.
//   responder.rs — Decision logic: given a set of findings, decide what tier
//                 of response is warranted, build a ResponsePackage, and
//                 either execute immediately (Tier 2-3) or queue for
//                 operator approval (Tier 4-5).

pub mod engine;
pub mod rules;
pub mod responder;

pub use engine::FirewallEngine;
pub use responder::Responder;
