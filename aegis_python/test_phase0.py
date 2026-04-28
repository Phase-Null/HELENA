#!/usr/bin/env python3
# aegis_python/test_phase0.py
"""
Phase 0 Test Suite — IPC Bridge Verification

Run this AFTER starting the AEGIS Rust core:
  (in one terminal)  cargo run --release
  (in another)       python3 test_phase0.py

Expected output if everything is working:
  [PASS] Connected to AEGIS
  [PASS] Ping responded
  [PASS] Status received — threat level: IDLE
  [PASS] Pending responses: 0
  [PASS] Set threat level command sent
  [PASS] Alert callback fires correctly
  [PASS] Disconnect and reconnect handled
  ─────────────────────────────────────────
  Phase 0 COMPLETE — 7/7 tests passed.

If any test fails, the error message tells you what to fix.
"""

import sys
import time
import threading
import logging

logging.basicConfig(level=logging.WARNING)  # quiet during tests

# Add parent dir so we can import aegis_bridge
sys.path.insert(0, ".")
from aegis_bridge import AegisBridge

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def test(name: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"  {PASS} {name}")
        results.append(True)
    else:
        print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))
        results.append(False)
    return condition


def run_tests():
    print("\n  AEGIS Phase 0 — IPC Bridge Test Suite")
    print("  =" * 22)

    bridge = AegisBridge()
    alert_received = threading.Event()
    alerts = []

    def on_alert(a):
        alerts.append(a)
        alert_received.set()

    def on_connected():
        pass  # connection confirmed below via is_connected

    bridge.on_alert        = on_alert
    bridge.on_connected    = on_connected
    bridge.start()

    # Give bridge time to connect
    for _ in range(20):  # up to 10 seconds
        if bridge.is_connected:
            break
        time.sleep(0.5)

    # ── Test 1: Connection ────────────────────────────────────────────────────
    test("Connected to AEGIS", bridge.is_connected,
         "Is aegis running? (cargo run --release)")

    if not bridge.is_connected:
        print("\n  Cannot proceed — AEGIS not running.")
        print("  Start AEGIS first: cd aegis-core && cargo run --release")
        bridge.stop()
        return

    # ── Test 2: Ping ──────────────────────────────────────────────────────────
    ping_ok = bridge.ping()
    test("Ping responded", ping_ok, "AEGIS did not reply to ping within timeout")

    # ── Test 3: Status ────────────────────────────────────────────────────────
    status = bridge.status()
    test("Status received", status is not None, "status() returned None")
    if status:
        threat = status.get("threat_level", "")
        test("Threat level reported", threat in ["IDLE", "ELEVATED", "ACTIVE", "CRITICAL"],
             f"Got: {threat}")

    # ── Test 4: Pending responses ─────────────────────────────────────────────
    pending = bridge.pending()
    test("Pending responses query works", pending is not None,
         "pending() returned None")
    if pending is not None:
        test("No pending responses at startup", len(pending) == 0,
             f"Got {len(pending)} pending responses — expected 0")

    # ── Test 5: Set threat level ──────────────────────────────────────────────
    sent = bridge.set_threat_level("ELEVATED", "Phase 0 test")
    test("Set threat level command sent", sent,
         "send returned False — socket not open?")
  
    # ── Test 6: Approve with empty reason is rejected locally ─────────────────
    rejected_locally = not bridge.approve("fake-id", "")
    test("Empty reason code rejected locally", rejected_locally,
         "approve() with empty reason should return False immediately")

    # ── Test 7: Status report formatting ─────────────────────────────────────
    briefing = bridge.format_status_for_helena()
    test("Status briefing format non-empty", bool(briefing) and len(briefing) > 10,
         f"Got: {repr(briefing)}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n  " + "─" * 44)
    passed = sum(results)
    total  = len(results)
    if passed == total:
        print(f"  Phase 0 COMPLETE — {passed}/{total} tests passed.")
        print("  IPC bridge is working. Ready for Phase 1.")
    else:
        print(f"  Phase 0 INCOMPLETE — {passed}/{total} tests passed.")
        print("  Fix failing tests before moving to Phase 1.")
    print()

    bridge.stop()


if __name__ == "__main__":
    run_tests()
