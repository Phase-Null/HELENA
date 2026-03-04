# helena_core/kernel/validation.py
"""
Multi-pass validation system for task verification
"""
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import logging
import hashlib
import json

logger = logging.getLogger(__name__)

class ValidationLevel(Enum):
    """Validation severity levels"""
    CRITICAL = auto()  # Must pass - security, safety
    HIGH = auto()      # Should pass - correctness
    MEDIUM = auto()    # Nice to have - quality
    LOW = auto()       # Optional - style, format

@dataclass
class ValidationIssue:
    """Individual validation issue"""
    level: ValidationLevel
    message: str
    code: str
    details: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.name,
            "message": self.message,
            "code": self.code,
            "details": self.details,
            "suggestion": self.suggestion
        }

@dataclass
class ValidationResult:
    """Result of validation chain"""
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    validation_time: float = 0.0
    validator_count: int = 0
    
    def add_issue(self, issue: ValidationIssue):
        """Add validation issue"""
        self.issues.append(issue)
        # Update passed status based on critical issues
        if issue.level == ValidationLevel.CRITICAL:
            self.passed = False
    
    def has_critical_issues(self) -> bool:
        """Check for critical issues"""
        return any(issue.level == ValidationLevel.CRITICAL for issue in self.issues)
    
    def get_issues_by_level(self, level: ValidationLevel) -> List[ValidationIssue]:
        """Get issues by severity level"""
        return [issue for issue in self.issues if issue.level == level]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
            "validation_time": self.validation_time,
            "validator_count": self.validator_count,
            "has_critical_issues": self.has_critical_issues()
        }

class Validator:
    """Base validator class"""
    
    def __init__(self, 
                 name: str,
                 level: ValidationLevel = ValidationLevel.MEDIUM,
                 enabled: bool = True):
        self.name = name
        self.level = level
        self.enabled = enabled
    
    def validate(self, task) -> List[ValidationIssue]:
        """Validate task, return list of issues"""
        if not self.enabled:
            return []
        
        try:
            return self._validate_impl(task)
        except Exception as e:
            logger.error(f"Validator {self.name} failed: {e}")
            return [ValidationIssue(
                level=ValidationLevel.CRITICAL,
                message=f"Validator {self.name} crashed: {str(e)}",
                code="VALIDATOR_ERROR"
            )]
    
    def _validate_impl(self, task) -> List[ValidationIssue]:
        """Implementation to be overridden by subclasses"""
        return []

class SecurityValidator(Validator):
    """Security-focused validator"""
    
    def __init__(self):
        super().__init__("SecurityValidator", ValidationLevel.CRITICAL)
        
        # Security patterns to check
        self.dangerous_patterns = [
            ("os.system", "SYSTEM_CALL"),
            ("subprocess.run", "SUBPROCESS"),
            ("__import__", "DYNAMIC_IMPORT"),
            ("eval(", "EVAL"),
            ("exec(", "EXEC"),
            ("compile(", "COMPILE"),
        ]
    
    def _validate_impl(self, task) -> List[ValidationIssue]:
        issues = []
        
        # Check for dangerous commands
        dangerous_commands = ["format_disk", "delete_all", "shutdown_system"]
        if task.command in dangerous_commands:
            issues.append(ValidationIssue(
                level=ValidationLevel.CRITICAL,
                message=f"Dangerous command detected: {task.command}",
                code="DANGEROUS_COMMAND",
                suggestion="Require explicit operator confirmation"
            ))
        
        # Check parameters for dangerous patterns
        params_str = json.dumps(task.parameters)
        for pattern, code in self.dangerous_patterns:
            if pattern in params_str:
                issues.append(ValidationIssue(
                    level=ValidationLevel.CRITICAL,
                    message=f"Dangerous pattern detected: {pattern}",
                    code=f"DANGEROUS_{code}",
                    details={"pattern": pattern, "context": "parameters"},
                    suggestion="Sanitize input or require additional validation"
                ))
        
        return issues

class SyntaxValidator(Validator):
    """Syntax and structure validator"""
    
    def __init__(self):
        super().__init__("SyntaxValidator", ValidationLevel.HIGH)
    
    def _validate_impl(self, task) -> List[ValidationIssue]:
        issues = []
        
        # Check required parameters
        required_params = self._get_required_params(task.command)
        for param in required_params:
            if param not in task.parameters:
                issues.append(ValidationIssue(
                    level=ValidationLevel.HIGH,
                    message=f"Missing required parameter: {param}",
                    code="MISSING_PARAMETER",
                    details={"parameter": param, "command": task.command},
                    suggestion=f"Add '{param}' parameter to request"
                ))
        
        # Validate parameter types
        for param_name, param_value in task.parameters.items():
            type_issue = self._validate_parameter_type(param_name, param_value, task.command)
            if type_issue:
                issues.append(type_issue)
        
        return issues
    
    def _get_required_params(self, command: str) -> List[str]:
        """Get required parameters for a command"""
        # This would be loaded from a schema database
        param_map = {
            "code_generate": ["language", "description"],
            "code_execute": ["code"],
            "memory_store": ["content"],
        }
        return param_map.get(command, [])
    
    def _validate_parameter_type(self, 
                                param_name: str, 
                                param_value: Any,
                                command: str) -> Optional[ValidationIssue]:
        """Validate parameter type"""
        # Simple type checking - would be more comprehensive
        type_rules = {
            "code": (str, "string"),
            "language": (str, "string"),
            "description": (str, "string"),
            "iterations": (int, "integer"),
            "timeout": (int, float, "number"),
        }
        
        expected_type = type_rules.get(param_name)
        if expected_type:
            type_classes, type_name = expected_type[:-1], expected_type[-1]
            if not isinstance(param_value, type_classes):
                return ValidationIssue(
                    level=ValidationLevel.HIGH,
                    message=f"Invalid type for parameter '{param_name}': expected {type_name}",
                    code="TYPE_MISMATCH",
                    details={
                        "parameter": param_name,
                        "expected_type": type_name,
                        "actual_type": type(param_value).__name__,
                        "value": str(param_value)[:100]
                    },
                    suggestion=f"Convert parameter to {type_name}"
                )
        
        return None

class ResourceValidator(Validator):
    """Resource usage validator"""
    
    def __init__(self):
        super().__init__("ResourceValidator", ValidationLevel.MEDIUM)
    
    def _validate_impl(self, task) -> List[ValidationIssue]:
        issues = []
        
        # Check resource budget compliance
        budget = task.context.resource_budget
        
        # Estimate resource requirements
        estimated = self._estimate_resource_requirements(task)
        
        # Compare with budget
        if estimated.get("cpu", 0) > budget.get("cpu", 100):
            issues.append(ValidationIssue(
                level=ValidationLevel.MEDIUM,
                message=f"CPU estimate ({estimated['cpu']}%) exceeds budget ({budget['cpu']}%)",
                code="CPU_OVERBUDGET",
                details={
                    "estimated": estimated["cpu"],
                    "budget": budget["cpu"],
                    "command": task.command
                },
                suggestion="Reduce task complexity or increase budget"
            ))
        
        if estimated.get("ram_mb", 0) > budget.get("ram_mb", 1024):
            issues.append(ValidationIssue(
                level=ValidationLevel.MEDIUM,
                message=f"RAM estimate ({estimated['ram_mb']}MB) exceeds budget ({budget['ram_mb']}MB)",
                code="RAM_OVERBUDGET",
                details={
                    "estimated": estimated["ram_mb"],
                    "budget": budget["ram_mb"],
                    "command": task.command
                },
                suggestion="Optimize memory usage or increase budget"
            ))
        
        return issues
    
    def _estimate_resource_requirements(self, task) -> Dict[str, float]:
        """Estimate resource requirements for task"""
        # Simple estimation based on command type
        estimates = {
            "code_generate": {"cpu": 30, "ram_mb": 256},
            "code_execute": {"cpu": 50, "ram_mb": 128},
            "memory_store": {"cpu": 10, "ram_mb": 64},
            "memory_retrieve": {"cpu": 20, "ram_mb": 128},
            "training_start": {"cpu": 80, "ram_mb": 1024},
        }
        
        return estimates.get(task.command, {"cpu": 25, "ram_mb": 128})

class ConsistencyValidator(Validator):
    """Consistency and logical validator"""
    
    def __init__(self):
        super().__init__("ConsistencyValidator", ValidationLevel.MEDIUM)
    
    def _validate_impl(self, task) -> List[ValidationIssue]:
        issues = []
        
        # Check for contradictory parameters
        contradictions = self._find_contradictions(task.parameters)
        for contradiction in contradictions:
            issues.append(ValidationIssue(
                level=ValidationLevel.MEDIUM,
                message=f"Parameter contradiction: {contradiction}",
                code="PARAMETER_CONTRADICTION",
                details={"contradiction": contradiction},
                suggestion="Review and reconcile parameter values"
            ))
        
        # Check for logical consistency with system state
        state_issues = self._check_system_state_consistency(task)
        issues.extend(state_issues)
        
        return issues
    
    def _find_contradictions(self, parameters: Dict[str, Any]) -> List[str]:
        """Find contradictory parameter values"""
        contradictions = []
        
        # Example: optimize_for both "speed" and "size"
        if "optimize_for" in parameters:
            value = parameters["optimize_for"]
            if isinstance(value, list):
                if "speed" in value and "size" in value:
                    contradictions.append("Cannot optimize for both speed and size simultaneously")
        
        # Example: timeout too short for expected operation
        if "timeout" in parameters and "operation" in parameters:
            timeout = parameters["timeout"]
            operation = parameters["operation"]
            
            if operation == "deep_analysis" and timeout < 10:
                contradictions.append(f"Deep analysis requires more than {timeout} seconds")
        
        return contradictions
    
    def _check_system_state_consistency(self, task) -> List[ValidationIssue]:
        """Check consistency with current system state"""
        issues = []
        
        # Example: Don't start training if system is in lockdown
        if task.command == "training_start" and task.context.environmental_state.get("lockdown", False):
            issues.append(ValidationIssue(
                level=ValidationLevel.HIGH,
                message="Cannot start training during system lockdown",
                code="STATE_INCONSISTENCY",
                details={
                    "command": task.command,
                    "system_state": "lockdown"
                },
                suggestion="Wait for lockdown to be lifted"
            ))
        
        return issues

class RegulatoryValidator(Validator):
    """Validator that delegates to the RegulatoryCore."""

    def __init__(self, regulatory_core):
        super().__init__("RegulatoryValidator", ValidationLevel.CRITICAL)
        self.regulatory_core = regulatory_core

    def _validate_impl(self, task) -> List[ValidationIssue]:
        violations = self.regulatory_core.check(task)
        issues: List[ValidationIssue] = []
        for v in violations:
            level = ValidationLevel.CRITICAL if v.blocked else ValidationLevel.HIGH
            issues.append(ValidationIssue(
                level=level,
                message=v.rule_description,
                code=f"REGULATORY_{v.rule_id}",
                details={"reason": v.reason, "rule_id": v.rule_id},
                suggestion="Blocked by regulatory rule" if v.blocked else "Advisory violation",
            ))
        return issues


class ValidationChain:
    """Chain of validators for multi-pass validation"""
    
    def __init__(self):
        self.validators: List[Validator] = []
        self.validation_cache = {}
        self.cache_size = 1000
    
    def setup_default_validators(self, regulatory_core=None):
        """Setup default validation chain, optionally with RegulatoryCore."""
        self.validators = [
            SecurityValidator(),
            SyntaxValidator(),
            ResourceValidator(),
            ConsistencyValidator(),
        ]
        if regulatory_core is not None:
            self.validators.insert(0, RegulatoryValidator(regulatory_core))
        logger.info("ValidationChain: loaded %d validators", len(self.validators))
    
    def add_validator(self, validator: Validator):
        """Add a validator to the chain"""
        self.validators.append(validator)
    
    def validate(self, task) -> ValidationResult:
        """Run validation chain on task"""
        start_time = time.time()
        
        # Check cache first
        cache_key = self._generate_cache_key(task)
        if cache_key in self.validation_cache:
            cached = self.validation_cache[cache_key]
            cached.validation_time = time.time() - start_time
            logger.debug("ValidationChain", f"Cache hit for task {task.task_id}")
            return cached
        
        # Create result
        result = ValidationResult(passed=True)
        result.validator_count = len(self.validators)
        
        # Run validators
        for validator in self.validators:
            if not result.passed and validator.level != ValidationLevel.CRITICAL:
                # Skip non-critical validators if already failed
                continue
            
            issues = validator.validate(task)
            for issue in issues:
                result.add_issue(issue)
        
        # Calculate validation time
        result.validation_time = time.time() - start_time
        
        # Cache result
        self._cache_result(cache_key, result)
        
        # Log validation result
        if result.passed:
            logger.debug("ValidationChain", 
                        f"Validation passed for task {task.task_id} in {result.validation_time:.3f}s")
        else:
            logger.warning("ValidationChain", 
                          f"Validation failed for task {task.task_id}: {len(result.issues)} issues")
        
        return result
    
    def _generate_cache_key(self, task) -> str:
        """Generate cache key for task"""
        # Create hash of task properties that affect validation
        key_data = {
            "command": task.command,
            "parameters_hash": hashlib.md5(
                json.dumps(task.parameters, sort_keys=True).encode()
            ).hexdigest(),
            "source": task.context.source,
            "mode": task.context.mode if hasattr(task.context, 'mode') else "unknown"
        }
        
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    
    def _cache_result(self, cache_key: str, result: ValidationResult):
        """Cache validation result"""
        self.validation_cache[cache_key] = result
        
        # Limit cache size
        if len(self.validation_cache) > self.cache_size:
            # Remove oldest entry (simplified - would use LRU in production)
            self.validation_cache.pop(next(iter(self.validation_cache)))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        cache_hits = sum(1 for r in self.validation_cache.values() if hasattr(r, 'cached'))
        
        return {
            "validators": len(self.validators),
            "cache_size": len(self.validation_cache),
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hits / max(len(self.validation_cache), 1)
        }
    
    def clear_cache(self):
        """Clear validation cache"""
        self.validation_cache.clear()
        logger.info("ValidationChain", "Validation cache cleared")
