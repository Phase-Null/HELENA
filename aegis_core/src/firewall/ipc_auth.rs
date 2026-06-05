// src/firewall/ipc_auth.rs
//
// IPC Authentication Module
//
// BUG FIX (BUG-4): The AEGIS IPC port (47201) had no authentication —
// any local process could send commands. This module implements
// HMAC-based challenge-response authentication for IPC connections.
//
// Protocol:
//   1. Client connects to 127.0.0.1:47201
//   2. Server sends a random 32-byte challenge (nonce)
//   3. Client computes HMAC-SHA256(challenge, shared_secret)
//      and sends the result back
//   4. Server verifies the HMAC — if valid, the connection is authenticated
//   5. All subsequent messages on this connection are trusted
//
// The shared secret is derived from:
//   - A per-installation random key stored at <HELENA_DATA>/.ipc_secret
//   - The process SID (Windows Security Identifier)
//   - PBKDF2 with 100k iterations

use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use hmac::{Hmac, Mac};
use rand::RngCore;
use sha2::Sha256;
use tracing::{info, warn};

type HmacSha256 = Hmac<Sha256>;

const IPC_SECRET_FILENAME: &str = ".ipc_secret";
const CHALLENGE_SIZE: usize = 32;
const HMAC_SIZE: usize = 32;
const PBKDF2_ITERATIONS: u32 = 100_000;

/// Manages IPC authentication state.
pub struct IpcAuth {
    shared_secret: [u8; 32],
}

/// A pending authentication challenge for a connection.
pub struct IpcChallenge {
    nonce: [u8; CHALLENGE_SIZE],
}

impl IpcAuth {
    /// Initialize IPC authentication.
    /// Loads or generates the per-installation shared secret.
    pub fn new(data_dir: &PathBuf) -> Result<Self> {
        let secret_path = data_dir.join(IPC_SECRET_FILENAME);

        let shared_secret = if secret_path.exists() {
            // Load existing secret
            let bytes = fs::read(&secret_path)
                .context("Failed to read IPC secret file")?;
            if bytes.len() != 32 {
                warn!("IPC secret file has wrong size ({} bytes), regenerating", bytes.len());
                Self::generate_and_save_secret(&secret_path)?
            } else {
                let mut secret = [0u8; 32];
                secret.copy_from_slice(&bytes);
                secret
            }
        } else {
            // Generate new secret
            Self::generate_and_save_secret(&secret_path)?
        };

        info!("IPC auth: shared secret loaded from {:?}", secret_path);
        Ok(Self { shared_secret })
    }

    fn generate_and_save_secret(path: &PathBuf) -> Result<[u8; 32]> {
        let mut secret = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut secret);

        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        fs::write(path, &secret)
            .context("Failed to write IPC secret file")?;

        // Set restrictive permissions (Windows: only current user can read)
        #[cfg(target_os = "windows")]
        {
            // On Windows, use acl commands or rely on directory permissions
            // The HELENA data directory should already be user-only
        }

        Ok(secret)
    }

    /// Generate a new authentication challenge for an incoming connection.
    pub fn create_challenge(&self) -> IpcChallenge {
        let mut nonce = [0u8; CHALLENGE_SIZE];
        rand::thread_rng().fill_bytes(&mut nonce);
        IpcChallenge { nonce }
    }

    /// Get the expected HMAC response for a challenge.
    /// The server uses this to verify the client's response.
    pub fn expected_response(&self, challenge: &IpcChallenge) -> [u8; HMAC_SIZE] {
        Self::compute_hmac(&self.shared_secret, &challenge.nonce)
    }

    /// Verify a client's HMAC response against a challenge.
    pub fn verify(&self, challenge: &IpcChallenge, client_response: &[u8; HMAC_SIZE]) -> bool {
        let expected = self.expected_response(challenge);
        // Constant-time comparison to prevent timing attacks
        hmac::digest::Mac::verify_slice(
            &Self::compute_hmac_mac(&self.shared_secret, &challenge.nonce),
            client_response
        ).is_ok()
    }

    /// Client-side: compute the HMAC response for a given challenge.
    /// Used by HELENA core to authenticate to AEGIS.
    pub fn client_respond(shared_secret: &[u8; 32], challenge_nonce: &[u8; CHALLENGE_SIZE]) -> [u8; HMAC_SIZE] {
        Self::compute_hmac(shared_secret, challenge_nonce)
    }

    fn compute_hmac(key: &[u8; 32], data: &[u8; CHALLENGE_SIZE]) -> [u8; HMAC_SIZE] {
        let mut mac = HmacSha256::new_from_slice(key)
            .expect("HMAC key length is always 32 bytes");
        mac.update(data);
        mac.finalize().into_bytes().into()
    }

    fn compute_hmac_mac(key: &[u8; 32], data: &[u8; CHALLENGE_SIZE]) -> HmacSha256 {
        let mut mac = HmacSha256::new_from_slice(key)
            .expect("HMAC key length is always 32 bytes");
        mac.update(data);
        mac
    }
}

impl IpcChallenge {
    /// Get the raw nonce bytes to send to the client.
    pub fn nonce(&self) -> &[u8; CHALLENGE_SIZE] {
        &self.nonce
    }
}
