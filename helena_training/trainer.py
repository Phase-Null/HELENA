"""
AutonomousTrainer – main orchestrator with real improvement flow.
"""
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from helena_core.utils.logging import get_logger
from .dataset import TrainingDataset
from .auditor import SecurityAuditor
from .pattern import PatternRecognizer
from .feedback import FeedbackLoopAnalyzer
from .refinement import ModelRefinementEngine
from .sandbox import Sandbox
from .log import ImprovementLog
from .scheduler import TrainingScheduler
from .introspect import CodeModel
from .improver import ImprovementGenerator
from .integration import IntegrationEngine
from .evolution import EvolutionDB
from .safety import SafetyGovernor

logger = get_logger()

class AutonomousTrainer:
    def __init__(self, kernel, runtime, memory, config_manager):
        self.kernel = kernel
        self.runtime = runtime
        self.memory = memory
        self.config = config_manager.get_section("training") or {}

        # Subcomponents
        self.dataset = TrainingDataset(
            str(Path.home() / '.helena' / 'training_data'),
            max_size=10000
        )
        self.auditor = SecurityAuditor({})
        self.pattern_recognizer = PatternRecognizer()
        self.feedback_analyzer = FeedbackLoopAnalyzer()
        self.refinement_engine = ModelRefinementEngine(kernel, memory)
        self.sandbox = Sandbox(Path(__file__).parent.parent)
        self.improvement_log = ImprovementLog(
            str(Path.home() / '.helena' / 'logs' / 'improvements.json')
        )
        self.scheduler = TrainingScheduler(self, self.config)
        self.code_model = CodeModel(Path(__file__).parent.parent)
        self.code_model.load_all()
        self.improver = ImprovementGenerator(self.code_model, self.dataset, self.kernel)
        self.integration = IntegrationEngine(Path(__file__).parent.parent)
        self.evolution = EvolutionDB(Path.home() / ".helena" / "evolution.db")
        self.safety = SafetyGovernor(self.config)

        self.enabled = True  # Training enabled by default
        self.active_session = False
        self.lock = threading.Lock()
        self.last_session_time = 0

        logger.info("AutonomousTrainer", "Initialized")

    def enable(self) -> None:
        self.enabled = True
        self.scheduler.start()
        logger.info("AutonomousTrainer", "Training enabled")

    def disable(self) -> None:
        self.enabled = False
        self.scheduler.stop()
        logger.info("AutonomousTrainer", "Training disabled")

    def is_training(self) -> bool:
        return self.active_session

    def start_session(self, focus_areas: Optional[List[str]] = None, reason: str = "manual") -> Dict[str, Any]:
        with self.lock:
            if not self.enabled and reason != "manual":
                return {"status": "error", "message": "Training not enabled"}
            if self.active_session:
                return {"status": "error", "message": "Session already active"}
            self.active_session = True

        logger.info("AutonomousTrainer", f"Starting training session (reason: {reason})")

        try:
            # 1. Collect data
            data = self._collect_data(focus_areas)

            # 2. Audit data
            if not self.auditor.audit_training_data(data):
                raise Exception("Training data failed security audit")

            # 3. Pattern recognition
            patterns = self.pattern_recognizer.analyze(data)
            loops = self.feedback_analyzer.identify_feedback_loops(patterns)

            # 4. Generate improvements
            proposals = self.improver.generate_proposals(focus_areas)

            # 5. Filter by safety
            safe_proposals = [p for p in proposals if self.safety.approve_patch(p)]

            # 6. Test each in sandbox
            valid_patches = []
            for patch in safe_proposals:
                test_result = self.sandbox.test_patch(patch)
                self.evolution.record_patch(patch, test_result, applied=False)
                if test_result['passed']:
                    valid_patches.append(patch)

            # 7. Integrate successful patches
            for patch in valid_patches:
                perf_before = test_result.get('performance_before', {})
                if self.integration.apply_patch(patch):
                    # After integration, we would reload modules (requires restart)
                    # For now, just log.
                    self.improvement_log.record(patch)
                    self.evolution.record_patch(patch, {'passed': True}, applied=True,
                                                perf_before=perf_before.get('response_time_ms'),
                                                perf_after=test_result.get('performance_after', {}).get('response_time_ms'))
                    logger.info("AutonomousTrainer", f"Applied patch: {patch['id']}")

            self.last_session_time = time.time()
            return {"status": "success", "improvements_applied": len(valid_patches)}

        except Exception as e:
            logger.error("AutonomousTrainer", f"Session failed: {e}")
            return {"status": "error", "message": str(e)}

        finally:
            self.active_session = False

    def _collect_data(self, focus_areas):
        data = {
            'timestamp': time.time(),
            'focus_areas': focus_areas or getattr(self.config, 'focus_areas', []),
            'sources': {}
        }
        if hasattr(self.kernel, 'learning_hook'):
            data['sources']['kernel'] = self.kernel.learning_hook.get_learning_data(limit=500)
        if self.runtime:
            data['sources']['runtime'] = self.runtime.get_system_status()
        if self.memory:
            data['sources']['memory'] = self.memory.get_stats()
        return data

    def get_status(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'active_session': self.active_session,
            'last_session_time': self.last_session_time,
            'improvement_stats': self.improvement_log.calculate_total_impact(),
            'dataset_stats': self.dataset.get_statistics(),
        }

