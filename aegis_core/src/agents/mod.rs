// src/agents/mod.rs
//
// Declares all agent modules and re-exports the public interface.
// main.rs imports from here.

pub mod base;
pub mod network;
pub mod integrity;
pub mod process;
pub mod intrusion;

pub use base::{Agent, AgentConfig, AgentReport, spawn_agent};
