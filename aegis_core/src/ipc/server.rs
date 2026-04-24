// src/ipc/server.rs
//
// The IPC server. AEGIS listens on 127.0.0.1:47201.
// HELENA connects as a client and keeps the connection open.
//
// Why TCP over a named pipe:
//   - Named pipes are Windows-only. TCP loopback works on both
//     Windows and Linux, so if we ever run AEGIS on Linux alongside
//     a Linux-hosted HELENA, nothing changes.
//   - TCP loopback is fast (~same latency as a named pipe on modern OS)
//   - Easier to debug (netcat into it if needed)
//
// The server handles one persistent connection from HELENA.
// If HELENA disconnects and reconnects, the server accepts the new connection.
// If AEGIS restarts, HELENA's reconnect loop picks it back up.
//
// All reads and writes use Tokio's async I/O.
// Messages are newline-delimited JSON.

use std::sync::Arc;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{TcpListener, TcpStream},
    sync::{mpsc, Mutex},
};
use tracing::{error, info, warn};

use super::protocol::{Message, MessageKind, MessageSource, StatusPayload};
use crate::state::AegisState;

pub const AEGIS_PORT: u16 = 47201;
pub const AEGIS_ADDR: &str = "127.0.0.1";

/// Handle to send messages to HELENA from anywhere in AEGIS.
/// Cloned and passed to agents that need to push alerts.
pub type AlertSender = mpsc::UnboundedSender<Message>;

pub struct IpcServer {
    state:  Arc<Mutex<AegisState>>,
    /// Channel for sending messages to the connected HELENA client.
    /// None if HELENA is not currently connected.
    helena_tx: Arc<Mutex<Option<AlertSender>>>,
}

impl IpcServer {
    pub fn new(state: Arc<Mutex<AegisState>>) -> (Self, Arc<Mutex<Option<AlertSender>>>) {
        let helena_tx = Arc::new(Mutex::new(None::<AlertSender>));
        let server = Self {
            state,
            helena_tx: helena_tx.clone(),
        };
        (server, helena_tx)
    }

    /// Run the TCP server. Accepts one connection at a time from HELENA.
    /// This is a long-running async task — spawn it with tokio::spawn.
    pub async fn run(self) -> anyhow::Result<()> {
        let addr = format!("{}:{}", AEGIS_ADDR, AEGIS_PORT);
        let listener = TcpListener::bind(&addr).await?;
        info!("AEGIS IPC listening on {}", addr);

        loop {
            match listener.accept().await {
                Ok((stream, peer)) => {
                    info!("HELENA connected from {}", peer);
                    self.handle_connection(stream).await;
                    info!("HELENA disconnected. Waiting for reconnect.");
                }
                Err(e) => {
                    error!("Accept error: {}", e);
                    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                }
            }
        }
    }

    async fn handle_connection(&self, stream: TcpStream) {
        // Split into read and write halves
        let (reader, writer) = stream.into_split();
        let mut lines = BufReader::new(reader).lines();

        // Create a channel so other parts of AEGIS can send to HELENA
        let (tx, mut rx) = mpsc::unbounded_channel::<Message>();

        // Register the sender so agents can push alerts
        {
            let mut lock = self.helena_tx.lock().await;
            *lock = Some(tx);
        }

        // Spawn the write task — drains the channel and writes to socket
        let mut writer = writer;
        let write_task = tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                match msg.to_line() {
                    Ok(line) => {
                        let with_newline = format!("{}\n", line);
                        if let Err(e) = writer.write_all(with_newline.as_bytes()).await {
                            error!("Write to HELENA failed: {}", e);
                            break;
                        }
                    }
                    Err(e) => {
                        error!("Failed to serialise message: {}", e);
                    }
                }
            }
        });

        // Read loop — handle incoming messages from HELENA
        loop {
            match lines.next_line().await {
                Ok(Some(line)) if !line.trim().is_empty() => {
                    match Message::from_line(&line) {
                        Ok(msg) => {
                            self.handle_message(msg).await;
                        }
                        Err(e) => {
                            warn!("Malformed message from HELENA: {} | raw: {}", e, &line[..line.len().min(100)]);
                        }
                    }
                }
                Ok(None) => {
                    // EOF — HELENA closed the connection
                    break;
                }
                Ok(Some(_)) => {} // empty line, skip
                Err(e) => {
                    error!("Read error: {}", e);
                    break;
                }
            }
        }

        // Clean up — remove the sender so no one tries to push to a dead connection
        {
            let mut lock = self.helena_tx.lock().await;
            *lock = None;
        }

        write_task.abort();
    }

    async fn handle_message(&self, msg: Message) {
        match msg.kind {
            MessageKind::Ping => {
                // Reply with Pong immediately
                let pong = Message::new(
                    MessageSource::Aegis,
                    MessageKind::Pong,
                    serde_json::json!({ "echo_id": msg.id }),
                );
                pong.id = msg.id.clone();
                self.send_to_helena(pong).await;
            }

            MessageKind::QueryStatus => {
                let state = self.state.lock().await;
                let payload = StatusPayload {
                    threat_level:      state.threat_level,
                    active_agents:     state.active_agent_count,
                    pending_responses: state.pending_responses.len() as u32,
                    uptime_seconds:    state.uptime_seconds(),
                    events_processed:  state.events_processed,
                    last_event_at:     state.last_event_at,
                };
                drop(state);

                let response = Message::new(
                    MessageSource::Aegis,
                    MessageKind::StatusReport,
                    serde_json::to_value(payload).unwrap_or_default(),
                );
                pong.id = msg.id.clone();
                self.send_to_helena(response).await;
            }

            MessageKind::QueryPending => {
                let state = self.state.lock().await;
                let pending: Vec<_> = state.pending_responses.values().collect();
                let payload = serde_json::json!({ "pending": pending });
                drop(state);

                let response = Message::new(
                    MessageSource::Aegis,
                    MessageKind::PendingReport,
                    payload,
                );
                pong.id = msg.id.clone();
                self.send_to_helena(response).await;
            }

            MessageKind::ApproveResponse => {
                if let Ok(approve) = serde_json::from_value::<super::protocol::ApprovePayload>(msg.payload) {
                    let result = {
                        let mut state = self.state.lock().await;
                        state.approve_response(&approve.package_id, &approve.reason_code, &approve.approved_by)
                    };
                    let response = Message::new(
                        MessageSource::Aegis,
                        MessageKind::ResponseExecuted,
                        serde_json::json!({ "ok": result, "package_id": approve.package_id }),
                    );
                    self.send_to_helena(response).await;
                }
            }

            MessageKind::RejectResponse => {
                if let Ok(reject) = serde_json::from_value::<super::protocol::RejectPayload>(msg.payload) {
                    let mut state = self.state.lock().await;
                    state.reject_response(&reject.package_id);
                }
            }

            MessageKind::SetThreatLevel => {
                if let Ok(set) = serde_json::from_value::<super::protocol::SetThreatPayload>(msg.payload) {
                    let mut state = self.state.lock().await;
                    state.set_threat_level(set.level);
                    info!("Threat level manually set to {} by HELENA: {}", set.level, set.reason);
                }
            }

            // These are AEGIS → HELENA only, shouldn't arrive from HELENA
            _ => {
                warn!("Unexpected message kind from HELENA: {:?}", msg.kind);
            }
        }
    }

    /// Send a message to HELENA if she's connected.
    /// If she's not connected, the message is silently dropped — it will be
    /// re-sent when relevant state is queried on reconnect.
    pub async fn send_to_helena(&self, msg: Message) {
        let lock = self.helena_tx.lock().await;
        if let Some(tx) = lock.as_ref() {
            if let Err(e) = tx.send(msg) {
                warn!("Failed to queue message for HELENA: {}", e);
            }
        }
        // Not connected — drop the message, log nothing.
        // HELENA will query current state on reconnect.
    }
}
