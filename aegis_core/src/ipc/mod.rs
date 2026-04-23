// src/ipc/mod.rs
pub mod protocol;
pub mod server;

pub use protocol::*;
pub use server::IpcServer;
