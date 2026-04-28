// src/etw/providers.rs
//
// Provider GUIDs, event IDs, and keyword bitmasks for every ETW provider
// AEGIS subscribes to.
//
// All GUIDs verified against:
//   logman query providers
//   Get-WinEvent -ListProvider * | Where-Object { $_.Name -like "*Kernel*" }
//
// Keyword values verified against provider manifests via:
//   logman query providers "Microsoft-Windows-Kernel-Process"

// ── Microsoft-Windows-Kernel-Process ─────────────────────────────────────────

/// GUID for Microsoft-Windows-Kernel-Process
pub const KERNEL_PROCESS_GUID: &str = "22fb2cd6-0e7b-422b-a0c7-2fad1fd0e716";

/// Keywords for Microsoft-Windows-Kernel-Process
/// These are bitmasks — OR them together for multiple event types
pub mod kernel_process {
    /// Process start and stop events (Event IDs 1, 2)
    pub const KEYWORD_PROCESS: u64 = 0x10;

    /// Thread start and stop events (Event IDs 3, 4)
    pub const KEYWORD_THREAD: u64 = 0x20;

    /// Image (DLL/EXE) load and unload events (Event ID 5)
    pub const KEYWORD_IMAGE: u64 = 0x40;

    /// CPU priority change events
    pub const KEYWORD_CPU_PRIORITY: u64 = 0x80;

    // Event IDs
    /// Process start — fired when a new process is created
    /// Fields: ProcessID (u32), ParentProcessID (u32), ImageFileName (String),
    ///         CommandLine (String), SessionID (u32)
    pub const EVENT_PROCESS_START: u16 = 1;

    /// Process stop — fired when a process exits
    /// Fields: ProcessID (u32), ExitCode (i32)
    pub const EVENT_PROCESS_STOP: u16 = 2;

    /// Image load — fired when a DLL or EXE is loaded into a process
    /// Fields: ProcessID (u32), ImageBase (u64), ImageSize (u32),
    ///         ImageChecksum (u32), ImageName (String)
    pub const EVENT_IMAGE_LOAD: u16 = 5;
}

// ── Microsoft-Windows-DNS-Client ─────────────────────────────────────────────

/// GUID for Microsoft-Windows-DNS-Client
pub const DNS_CLIENT_GUID: &str = "1c95126e-7eea-49a9-a3fe-a378b03ddb4d";

pub mod dns_client {
    /// Enable all DNS events
    pub const KEYWORD_ALL: u64 = 0xFFFFFFFFFFFFFFFF;

    /// DNS query response event
    /// Fields: QueryName (String), QueryType (u32), QueryStatus (u32),
    ///         QueryResults (String — semicolon-separated IPs)
    pub const EVENT_DNS_QUERY: u16 = 3006;
}

// ── Microsoft-Windows-Security-Auditing ──────────────────────────────────────

/// GUID for Microsoft-Windows-Security-Auditing
/// Note: this is a "restricted" provider — admin rights required
pub const SECURITY_AUDITING_GUID: &str = "54849625-5478-4994-a5ba-3e3b0328c30d";

pub mod security_auditing {
    pub const KEYWORD_ALL: u64 = 0xFFFFFFFFFFFFFFFF;

    /// Failed login attempt
    pub const EVENT_LOGON_FAILURE: u16 = 4625;

    /// Special privileges assigned to a new logon
    pub const EVENT_SPECIAL_LOGON: u16 = 4672;

    /// New process created (requires "Audit Process Creation" policy enabled)
    pub const EVENT_PROCESS_CREATED: u16 = 4688;

    /// Account lockout
    pub const EVENT_ACCOUNT_LOCKED: u16 = 4740;
}

// ── Suspicious indicators ─────────────────────────────────────────────────────
//
// These are checked inside ETW callbacks against process image names
// and command lines. Kept here so they can be updated without touching
// the consumer logic.

/// Process image names that are immediately suspicious when seen created.
/// Checked against the full image path (lowercase) using contains().
pub const SUSPICIOUS_IMAGE_PATHS: &[&str] = &[
    "mimikatz",
    "msfconsole",
    "metasploit",
    "psexec",
    "wce.exe",
    "pwdump",
    "procdump",  // legitimate tool but often abused
    "\\temp\\",
    "\\appdata\\local\\temp\\",
    "\\windows\\temp\\",
    "\\downloads\\",
];

/// Command line fragments that suggest malicious intent.
/// Checked against CommandLine field (lowercase).
pub const SUSPICIOUS_CMDLINE_FRAGMENTS: &[&str] = &[
    "-enc ",        // PowerShell encoded command (base64 payload)
    "-encodedcommand",
    "invoke-mimikatz",
    "invoke-expression",
    "downloadstring",
    "net user /add",
    "net localgroup administrators",
    "reg add.*run",  // adding to Run key for persistence
    "schtasks /create",
    "bitsadmin /transfer",
];

/// DNS names that suggest C2 or malicious activity.
/// Checked as substrings of the query name.
pub const SUSPICIOUS_DNS_PATTERNS: &[&str] = &[
    ".onion.",     // Tor (usually tunnelled — seeing this in DNS is suspicious)
    "ngrok.io",    // legitimate tunnelling tool, often abused for C2
    ".ngrok.",
    "serveo.net",  // another tunnelling service
    "localhost.run",
    ".dyn.dns.",
    "no-ip.",
    "dyndns.",
];
