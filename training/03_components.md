# HELENA Self‑Training System – Component Specifications

This document provides detailed class interfaces for each major component of the training system. All classes reside in the `helena_training` package.

## 1. `TrainingDataset`

Manages the storage and retrieval of training data.

```python
class TrainingDataset:
    def __init__(self, storage_path: str, max_size: int = 10000):
        """
        :param storage_path: Directory for encrypted storage.
        :param max_size: Maximum number of entries per dataset.
        """
    
    def add(self, data_type: str, data: Dict[str, Any]) -> None:
        """Add a single data point to the specified dataset."""
    
    def add_batch(self, data_type: str, batch: List[Dict[str, Any]]) -> None:
        """Add multiple data points efficiently."""
    
    def get_recent(self, data_type: str, n: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent n entries of a given type."""
    
    def get_statistics(self) -> Dict[str, Any]:
        """Return size, oldest/newest timestamps for each dataset."""

class SecurityAuditor:
    def __init__(self, security_policies: Dict[str, Any]):
        self.policies = security_policies
    
    def audit_training_data(self, data: Dict[str, Any]) -> bool:
        """
        Scan data for malicious patterns, data leakage, integrity issues.
        Returns True if safe, False otherwise.
        """
    
    def validate_improvement(self, improvement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check a proposed improvement against security rules.
        Returns a dict with 'passed' (bool), 'warnings' (list), and 'checks' (list).
        """

class PatternRecognizer:
    def __init__(self):
        self.algorithms = {
            'temporal': TemporalPatternRecognizer(),
            'semantic': SemanticPatternRecognizer(),
            'structural': StructuralPatternRecognizer(),
        }
    
    def analyze(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Return a list of patterns, each with:
          - type: str
          - confidence: float (0-1)
          - source: str (which algorithm found it)
          - details: dict
        """

class FeedbackLoopAnalyzer:
    def __init__(self):
        self.history = deque(maxlen=1000)
    
    def identify_feedback_loops(self, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyse decision chains extracted from patterns.
        Returns a list of loops, each with:
          - type: 'positive' | 'negative'
          - chain: list of decision steps
          - strength: float
          - impact: float (estimated effect on system)
        """
    
    def improve_decision_making(self, kernel_data: Dict[str, Any], loops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate improvement suggestions based on loop analysis.
        """

class SoftwareEngineeringImprover:
    def __init__(self):
        self.code_patterns = {}
        self.best_practices = self._load_best_practices()
    
    def refine_code_generation(self, code_data: Dict[str, Any], patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyse successful and failed code executions to generate improvements.
        Returns a list of improvement dicts.
        """

class ModelRefinementEngine:
    def __init__(self, kernel, memory):
        self.kernel = kernel
        self.memory = memory
        self.improvers = {
            'code': SoftwareEngineeringImprover(),
            'decision': FeedbackLoopAnalyzer(),
            'memory': MemoryOptimizer(),
        }
    
    def generate_improvements(self, patterns: List[Dict[str, Any]], feedback_loops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Iterate over improvers and collect candidate improvements.
        Each improvement includes:
          - id: str
          - type: str
          - parameters: dict (what to change)
          - expected_impact: float
          - requires_restart: bool
        """

class SandboxTester:
    def __init__(self, kernel_snapshot, baseline_metrics):
        self.kernel_snapshot = kernel_snapshot
        self.baseline = baseline_metrics
    
    def test_improvement(self, improvement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply improvement to a copy of the kernel, run a test suite.
        Returns:
          - passed: bool
          - performance_delta: float
          - security_check: dict
          - logs: str
        """

class ImprovementLog:
    def __init__(self, storage_path: str):
        self.path = storage_path
    
    def record(self, improvement: Dict[str, Any]) -> None:
        """Store an applied improvement with timestamp."""
    
    def get_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Return improvements from the last N days."""
    
    def calculate_total_impact(self) -> Dict[str, float]:
        """Aggregate impact by improvement type."""

class TrainingScheduler:
    def __init__(self, trainer, config):
        self.trainer = trainer
        self.schedule = self._parse_config(config)
    
    def check_and_start(self) -> bool:
        """Check current time and system state; start training if conditions met."""
    
    def set_operator_schedule(self, schedule: Dict[str, Any]) -> None:
        """Update schedule from operator preferences."""

class AutonomousTrainer:
    def __init__(self, kernel, runtime, memory, config):
        self.kernel = kernel
        self.runtime = runtime
        self.memory = memory
        self.config = config
        
        self.dataset = TrainingDataset(config['storage_path'])
        self.auditor = SecurityAuditor(config['security_policies'])
        self.pattern_recognizer = PatternRecognizer()
        self.feedback_analyzer = FeedbackLoopAnalyzer()
        self.refinement_engine = ModelRefinementEngine(kernel, memory)
        self.tester = SandboxTester()
        self.improvement_log = ImprovementLog(config['log_path'])
        self.scheduler = TrainingScheduler(self, config['schedule'])
    
    def enable(self) -> None:
        """Activate autonomous training."""
    
    def disable(self) -> None:
        """Deactivate training."""
    
    def start_session(self, focus_areas: List[str] = None) -> Dict[str, Any]:
        """Run a full training session."""
    
    def _collect_data(self, focus_areas) -> Dict[str, Any]:
        """Gather recent data from kernel hooks, memory, runtime."""
    
    def _audit_data(self, data) -> bool:
        """Delegate to SecurityAuditor."""
    
    def _analyze_patterns(self, data) -> Tuple[List, List]:
        """Run pattern recognition and feedback analysis."""
    
    def _refine_models(self, patterns, loops) -> List:
        """Generate improvements."""
    
    def _validate_improvements(self, improvements) -> List:
        """Test each improvement in sandbox, return only passing ones."""
    
    def _integrate_improvements(self, improvements) -> Dict:
        """Apply improvements, log them, handle rollback."""
    
    def get_status(self) -> Dict[str, Any]:
        """Return current training state, last session info, improvement stats."""

        
