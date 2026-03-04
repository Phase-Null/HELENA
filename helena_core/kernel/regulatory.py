# helena_core/kernel/regulatory.py
"""
HELENA Regulatory Core – embedded ethical constraints with operator
control emphasis.

Three layers of rules
---------------------
1. **Absolute prohibitions** – hard-coded, cannot be overridden.
   e.g. "never exfiltrate operator data", "never disable kill-switch".
2. **Operator-controlled constraints** – toggleable by the operator.
   e.g. "allow network scanning", "allow code execution".
3. **Soft guidelines** – advisory, logged but not blocking.
   e.g. "prefer minimal resource usage", "prefer deterministic output".

The RegulatoryCore plugs into the ValidationChain as a CRITICAL-level
validator so that every task is checked before execution.
"""
import time
import logging
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Rule definitions ──────────────────────────────────────────────

class RuleLevel(Enum):
    ABSOLUTE = auto()       # Cannot be overridden
    OPERATOR = auto()       # Operator can toggle
    ADVISORY = auto()       # Logged, not enforced


@dataclass
class Rule:
    """A single regulatory rule."""
    id: str
    description: str
    level: RuleLevel
    enabled: bool = True
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "level": self.level.name,
            "enabled": self.enabled,
            "tags": self.tags,
        }


@dataclass
class Violation:
    """Record of a rule violation."""
    rule_id: str
    rule_description: str
    level: RuleLevel
    task_command: str
    reason: str
    timestamp: float = field(default_factory=time.time)
    blocked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.rule_description,
            "level": self.level.name,
            "command": self.task_command,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "blocked": self.blocked,
        }


# ── Core ──────────────────────────────────────────────────────────

class RegulatoryCore:
    """
    Embedded ethical constraint engine.

    Usage::

        reg = RegulatoryCore()
        violations = reg.check(task)
        if reg.should_block(violations):
            # reject the task
    """

    def __init__(self) -> None:
        self._rules: Dict[str, Rule] = {}
        self._violations: List[Violation] = []
        self._max_violations = 5000
        self._operator_name: str = ""
        self._load_default_rules()
        logger.info("RegulatoryCore initialised (%d rules)", len(self._rules))

    # ── Default rules ─────────────────────────────────────────────

    def _load_default_rules(self) -> None:
        """Load the built-in rule set."""
        absolutes = [
            Rule("ABS-001", "Never exfiltrate operator data to external endpoints",
                 RuleLevel.ABSOLUTE, tags=["security", "privacy"]),
            Rule("ABS-002", "Never disable the kill-switch or bypass shutdown stages",
                 RuleLevel.ABSOLUTE, tags=["security", "safety"]),
            Rule("ABS-003", "Never modify operator authentication or access controls",
                 RuleLevel.ABSOLUTE, tags=["security"]),
            Rule("ABS-004", "Never execute commands that destroy the host filesystem",
                 RuleLevel.ABSOLUTE, tags=["safety"]),
            Rule("ABS-005", "Never impersonate the operator or forge credentials",
                 RuleLevel.ABSOLUTE, tags=["security", "integrity"]),
            Rule("ABS-006", "Never remove or weaken regulatory rules at runtime",
                 RuleLevel.ABSOLUTE, tags=["integrity"]),
            Rule("ABS-007", "Never send data to remote servers without operator consent",
                 RuleLevel.ABSOLUTE, tags=["privacy"]),
            Rule("ABS-008", "Never train on operator private data without explicit permission",
                 RuleLevel.ABSOLUTE, tags=["privacy", "training"]),
        ]
        operator_rules = [
            Rule("OPR-001", "Allow network scanning capabilities",
                 RuleLevel.OPERATOR, enabled=False, tags=["network"]),
            Rule("OPR-002", "Allow arbitrary code execution via sandbox",
                 RuleLevel.OPERATOR, enabled=True, tags=["code"]),
            Rule("OPR-003", "Allow autonomous self-upgrade without confirmation",
                 RuleLevel.OPERATOR, enabled=False, tags=["training"]),
            Rule("OPR-004", "Allow file system write operations outside project",
                 RuleLevel.OPERATOR, enabled=False, tags=["filesystem"]),
            Rule("OPR-005", "Allow module hot-loading from untrusted sources",
                 RuleLevel.OPERATOR, enabled=False, tags=["modules"]),
        ]
        advisories = [
            Rule("ADV-001", "Prefer minimal resource usage when idle",
                 RuleLevel.ADVISORY, tags=["performance"]),
            Rule("ADV-002", "Prefer deterministic output for reproducibility",
                 RuleLevel.ADVISORY, tags=["quality"]),
            Rule("ADV-003", "Log all security-relevant decisions",
                 RuleLevel.ADVISORY, tags=["audit"]),
        ]
        for rule in absolutes + operator_rules + advisories:
            self._rules[rule.id] = rule

    # ── Checking ──────────────────────────────────────────────────

    def check(self, task) -> List[Violation]:
        """
        Check a task against all enabled rules.

        *task* should have at least ``.command`` and ``.parameters`` attrs.
        Returns a list of violations (may be empty).
        """
        violations: List[Violation] = []
        command = getattr(task, "command", "")
        params = getattr(task, "parameters", {})
        params_str = str(params).lower()

        for rule in self._rules.values():
            if not rule.enabled:
                continue
            violation = self._evaluate_rule(rule, command, params, params_str)
            if violation is not None:
                violations.append(violation)

        # Store violations
        self._violations.extend(violations)
        if len(self._violations) > self._max_violations:
            self._violations = self._violations[-self._max_violations:]

        return violations

    def _evaluate_rule(self, rule: Rule, command: str,
                       params: Dict[str, Any],
                       params_str: str) -> Optional[Violation]:
        """Evaluate a single rule against the task."""
        # ── Absolute rules ────────────────────────────────────────
        if rule.id == "ABS-001":
            if "exfiltrate" in params_str or "send_external" in command:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Data exfiltration detected", blocked=True)

        if rule.id == "ABS-002":
            if "disable_kill" in params_str or "bypass_shutdown" in command:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Kill-switch bypass attempted", blocked=True)

        if rule.id == "ABS-003":
            if "modify_auth" in command or "change_password" in params_str:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Auth modification attempted", blocked=True)

        if rule.id == "ABS-004":
            destructive = {"rm -rf /", "format_disk", "destroy_filesystem",
                           "del /s /q", "mkfs"}
            if command in destructive or any(d in params_str for d in destructive):
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Destructive filesystem op", blocked=True)

        if rule.id == "ABS-005":
            if "impersonate" in params_str or "forge_credential" in command:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Impersonation attempted", blocked=True)

        if rule.id == "ABS-006":
            if "remove_rule" in command or "weaken_regulation" in params_str:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Regulatory weakening attempted", blocked=True)

        # ── Operator rules ────────────────────────────────────────
        if rule.id == "OPR-001" and not rule.enabled:
            if "network_scan" in command or "port_scan" in params_str:
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Network scanning not enabled by operator")

        if rule.id == "OPR-004" and not rule.enabled:
            target = params.get("path", "")
            if isinstance(target, str) and target and not target.startswith("."):
                # Heuristic: absolute path outside project
                if target.startswith("/") and "helena" not in target.lower():
                    return Violation(rule.id, rule.description, rule.level,
                                     command, "Write outside project tree")

        if rule.id == "OPR-005" and not rule.enabled:
            if "load_module" in command and params.get("source") == "untrusted":
                return Violation(rule.id, rule.description, rule.level,
                                 command, "Untrusted module loading not allowed")

        return None

    def should_block(self, violations: List[Violation]) -> bool:
        """Return True if any violation is blocking (ABSOLUTE level)."""
        return any(v.blocked or v.level == RuleLevel.ABSOLUTE for v in violations)

    # ── Operator controls ─────────────────────────────────────────

    def set_operator(self, name: str) -> None:
        self._operator_name = name

    def enable_rule(self, rule_id: str) -> bool:
        """Enable an operator-level rule.  Absolute rules are always on."""
        rule = self._rules.get(rule_id)
        if rule and rule.level == RuleLevel.OPERATOR:
            rule.enabled = True
            logger.info("Rule %s enabled by operator", rule_id)
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable an operator-level rule.  Absolute rules cannot be disabled."""
        rule = self._rules.get(rule_id)
        if rule and rule.level == RuleLevel.OPERATOR:
            rule.enabled = False
            logger.info("Rule %s disabled by operator", rule_id)
            return True
        if rule and rule.level == RuleLevel.ABSOLUTE:
            logger.warning("Cannot disable absolute rule %s", rule_id)
        return False

    # ── Queries ───────────────────────────────────────────────────

    def list_rules(self, level: Optional[RuleLevel] = None) -> List[Dict[str, Any]]:
        rules = self._rules.values()
        if level:
            rules = [r for r in rules if r.level == level]
        return [r.to_dict() for r in rules]

    def get_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [v.to_dict() for v in self._violations[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._violations)
        blocked = sum(1 for v in self._violations if v.blocked)
        by_level: Dict[str, int] = {}
        for v in self._violations:
            key = v.level.name
            by_level[key] = by_level.get(key, 0) + 1
        return {
            "total_rules": len(self._rules),
            "total_violations": total,
            "blocked_violations": blocked,
            "by_level": by_level,
        }
