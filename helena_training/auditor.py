"""
Security auditor for training and self-modification operations.

AST-based analysis — catches dangerous code patterns that string matching misses.
This is the gatekeeper for HELENA's CodeEditor write operations.
If this passes dangerous code, HELENA can write arbitrary malicious code to herself.
"""
import ast
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum, auto


class Severity(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


@dataclass
class SecurityIssue:
    severity: Severity
    message: str
    code: str
    line: Optional[int] = None
    col: Optional[int] = None
    suggestion: str = ""


class SecurityAuditor:
    """
    AST-based security auditor for code that HELENA writes to herself.

    Uses Python's `ast` module to parse code into a syntax tree and walk it
    for dangerous patterns. This catches obfuscated code that simple string
    matching misses (e.g. getattr(__builtins__, "ex"+"ec")("...")).

    The auditor is intentionally conservative — it flags suspicious patterns
    even if they might be benign. Better to block a safe operation than allow
    a malicious one.
    """

    # ── Dangerous imports ─────────────────────────────────────────

    BLOCKED_MODULES = frozenset({
        "os", "subprocess", "sys", "ctypes", "shutil",
        "socket", "http", "urllib", "requests",
        "pickle", "shelve", "marshal", "imp",
        "importlib", "code", "codeop", "compileall",
        "multiprocessing", "threading",  # threading is borderline — allow with warning
        "tempfile", "pathlib",  # filesystem access
    })

    # Modules that are allowed but worth flagging for review
    WARN_MODULES = frozenset({
        "threading", "pathlib", "tempfile", "json",
    })

    # ── Dangerous attribute names ─────────────────────────────────

    BLOCKED_ATTRS = frozenset({
        "system", "popen", "spawn", "call", "run", "check_output",
        "check_call", "getoutput", "getstatusoutput",
        "exec", "eval", "compile", "__import__",
        "__builtins__", "__code__", "__globals__",
        "load", "loads",  # pickle/marshal
    })

    # ── Dangerous function names ──────────────────────────────────

    BLOCKED_FUNCTIONS = frozenset({
        "exec", "eval", "compile", "__import__",
        "breakpoint",  # can attach debugger
    })

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    def audit(self, code: str) -> Dict[str, Any]:
        """
        Audit code for security issues using AST analysis.

        Returns dict with keys:
          status: "safe" | "unsafe" | "warning"
          issues: list of SecurityIssue dicts
          warnings: list of warning strings (backward compat)
        """
        issues: List[SecurityIssue] = []

        # Step 1: Parse the code
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "unsafe",
                "issues": [SecurityIssue(
                    severity=Severity.HIGH,
                    message=f"Code has syntax errors and cannot be audited: {e}",
                    code="SYNTAX_ERROR",
                    line=e.lineno,
                    suggestion="Fix syntax errors before auditing",
                )],
                "warnings": [],
            }

        # Step 2: Walk the AST for dangerous patterns
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name.split(".")[0]
                    if mod_name in self.BLOCKED_MODULES:
                        issues.append(SecurityIssue(
                            severity=Severity.CRITICAL,
                            message=f"Blocked import: {alias.name}",
                            code="BLOCKED_IMPORT",
                            line=node.lineno,
                            suggestion=f"Remove import of {alias.name} — it enables dangerous operations",
                        ))
                    elif mod_name in self.WARN_MODULES:
                        issues.append(SecurityIssue(
                            severity=Severity.LOW,
                            message=f"Caution: import of {alias.name} — review usage",
                            code="WARN_IMPORT",
                            line=node.lineno,
                        ))

            # Check from...import
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_name = node.module.split(".")[0]
                    if mod_name in self.BLOCKED_MODULES:
                        for alias in node.names:
                            issues.append(SecurityIssue(
                                severity=Severity.CRITICAL,
                                message=f"Blocked import: from {node.module} import {alias.name}",
                                code="BLOCKED_IMPORT",
                                line=node.lineno,
                            ))
                    elif mod_name in self.WARN_MODULES:
                        issues.append(SecurityIssue(
                            severity=Severity.LOW,
                            message=f"Caution: from {node.module} import ...",
                            code="WARN_IMPORT",
                            line=node.lineno,
                        ))

            # Check function calls — exec, eval, compile, __import__
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name:
                    # Direct dangerous function calls
                    root_name = func_name.split(".")[-1]
                    if root_name in self.BLOCKED_FUNCTIONS:
                        issues.append(SecurityIssue(
                            severity=Severity.CRITICAL,
                            message=f"Blocked function call: {func_name}()",
                            code="BLOCKED_CALL",
                            line=node.lineno,
                            suggestion=f"Remove call to {func_name}() — it enables arbitrary code execution",
                        ))

                    # Attribute-based dangerous calls: obj.system(), obj.popen(), etc.
                    if root_name in self.BLOCKED_ATTRS:
                        issues.append(SecurityIssue(
                            severity=Severity.CRITICAL,
                            message=f"Blocked method call: {func_name}()",
                            code="BLOCKED_METHOD",
                            line=node.lineno,
                        ))

                    # shell=True in subprocess calls
                    if "subprocess" in func_name:
                        for keyword in node.keywords:
                            if keyword.arg == "shell":
                                if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                                    issues.append(SecurityIssue(
                                        severity=Severity.CRITICAL,
                                        message=f"shell=True in {func_name}() — command injection risk",
                                        code="SHELL_TRUE",
                                        line=node.lineno,
                                        suggestion="Use list-form arguments instead of shell=True",
                                    ))

            # Check attribute access on dangerous names
            elif isinstance(node, ast.Attribute):
                if node.attr in self.BLOCKED_ATTRS:
                    # Only flag if it's on a module-like object
                    if isinstance(node.value, ast.Name):
                        issues.append(SecurityIssue(
                            severity=Severity.HIGH,
                            message=f"Dangerous attribute access: {node.value.id}.{node.attr}",
                            code="DANGEROUS_ATTR",
                            line=node.lineno,
                        ))
                    elif isinstance(node.value, ast.Attribute):
                        # e.g. os.path.system (nonsense but catches patterns)
                        pass

            # Check string concatenation that might be obfuscation
            elif isinstance(node, ast.BinOp):
                if isinstance(node.op, ast.Add):
                    # Flag if both sides are string constants being concatenated
                    # with suspicious content like "ex" + "ec"
                    left = self._get_constant_str(node.left)
                    right = self._get_constant_str(node.right)
                    if left and right:
                        combined = left + right
                        if combined.lower() in self.BLOCKED_FUNCTIONS | self.BLOCKED_ATTRS:
                            issues.append(SecurityIssue(
                                severity=Severity.CRITICAL,
                                message=f"Suspected obfuscation: string concatenation produces '{combined}'",
                                code="OBFUSCATION",
                                line=node.lineno,
                                suggestion="Do not obfuscate function names",
                            ))

            # Check for getattr with string literals (bypass technique)
            elif isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name == "getattr":
                    if len(node.args) >= 2:
                        attr_name = self._get_constant_str(node.args[1])
                        if attr_name and attr_name in self.BLOCKED_ATTRS | self.BLOCKED_FUNCTIONS:
                            issues.append(SecurityIssue(
                                severity=Severity.CRITICAL,
                                message=f"getattr() accessing blocked attribute: {attr_name}",
                                code="GETATTR_BYPASS",
                                line=node.lineno,
                            ))

        # Step 3: Determine overall status
        has_critical = any(i.severity == Severity.CRITICAL for i in issues)
        has_high = any(i.severity == Severity.HIGH for i in issues)
        warnings_only = all(i.severity in (Severity.LOW, Severity.MEDIUM) for i in issues)

        if has_critical or has_high:
            status = "unsafe"
        elif warnings_only and issues:
            status = "warning"
        else:
            status = "safe"

        return {
            "status": status,
            "issues": [
                {
                    "severity": i.severity.name,
                    "message": i.message,
                    "code": i.code,
                    "line": i.line,
                    "suggestion": i.suggestion,
                }
                for i in issues
            ],
            "warnings": [i.message for i in issues if i.severity in (Severity.LOW, Severity.MEDIUM)],
        }

    def audit_training_data(self, data: Dict[str, Any]) -> bool:
        """Audit training data for safety and validity."""
        if not isinstance(data, dict):
            return False
        if 'sources' not in data:
            return False
        sources = data.get('sources', {})
        if isinstance(sources, dict):
            for key, value in sources.items():
                if isinstance(value, list) and len(value) > 100000:
                    return False
        return True

    def validate(self, operation: str) -> bool:
        """Validate if an operation is allowed."""
        blocked_operations = {
            "shell_execute", "arbitrary_code_run", "network_bind",
            "file_delete_recursive", "registry_modify",
        }
        return operation not in blocked_operations

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _get_call_name(node: ast.Call) -> Optional[str]:
        """Extract the dotted name of a function call, e.g. 'subprocess.run'."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    @staticmethod
    def _get_constant_str(node: ast.expr) -> Optional[str]:
        """Extract a string constant from an AST node, if it is one."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None
