#!/usr/bin/env python3
"""
helena_firewall_cleanup.py

Removes all Windows Firewall rules created by HELENA/AEGIS.
All HELENA rules are prefixed with HELENA_BLOCK_ so they're easy to identify.

Must be run as administrator.

Usage:
    python helena_firewall_cleanup.py           # interactive — asks before deleting
    python helena_firewall_cleanup.py --force   # no prompt, just deletes
    python helena_firewall_cleanup.py --list    # list only, don't delete

Can also be dropped into HELENA's tools so she can run it on command.
"""

import subprocess
import sys
import argparse
from typing import List


HELENA_RULE_PREFIX = "HELENA_BLOCK_"


def get_helena_rules() -> List[str]:
    """
    Query Windows Firewall for all rules with the HELENA prefix.
    Returns a list of rule names.
    """
    try:
        result = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "show", "rule",
                f"name={HELENA_RULE_PREFIX}*",
                "verbose"
            ],
            capture_output=True,
            text=True,
            timeout=15
        )
    except FileNotFoundError:
        print("ERROR: netsh not found. Are you running on Windows?")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("ERROR: netsh timed out.")
        sys.exit(1)

    # Parse rule names from output
    # netsh output format: "Rule Name:                            HELENA_BLOCK_..."
    rules = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Rule Name:"):
            name = line.split(":", 1)[1].strip()
            if name.startswith(HELENA_RULE_PREFIX):
                rules.append(name)

    return rules


def delete_rule(rule_name: str) -> bool:
    """Delete a single firewall rule by name. Returns True on success."""
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={rule_name}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  ERROR deleting {rule_name}: {e}")
        return False


def check_admin() -> bool:
    """Check if running as administrator."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Remove all HELENA/AEGIS firewall rules"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Delete without prompting"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List rules only, do not delete"
    )
    args = parser.parse_args()

    print("HELENA Firewall Cleanup Utility")
    print("=" * 40)

    # Admin check
    if not check_admin():
        print("\nWARNING: Not running as administrator.")
        print("Deletion will likely fail. Right-click and run as administrator.")
        print()

    # Find rules
    print("Scanning for HELENA firewall rules...")
    rules = get_helena_rules()

    if not rules:
        print("No HELENA firewall rules found. Nothing to clean up.")
        return

    print(f"\nFound {len(rules)} HELENA firewall rule{'s' if len(rules) != 1 else ''}:\n")
    for rule in rules:
        print(f"  {rule}")

    if args.list:
        print("\n(--list mode: no rules deleted)")
        return

    # Confirm unless --force
    if not args.force:
        print()
        confirm = input(f"Delete all {len(rules)} rules? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Delete
    print("\nDeleting rules...")
    success = 0
    failed  = 0

    for rule in rules:
        if delete_rule(rule):
            print(f"  [OK]   {rule}")
            success += 1
        else:
            print(f"  [FAIL] {rule}")
            failed += 1

    print(f"\nDone. {success} deleted, {failed} failed.")

    if failed > 0:
        print("Some rules failed to delete. Make sure you're running as administrator.")


if __name__ == "__main__":
    main()
