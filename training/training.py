# helena_training/trainer.py (extended)
from .introspect import CodeModel
from .improver import ImprovementGenerator
from .sandbox import Sandbox
from .integration import IntegrationEngine
from .evolution import EvolutionDB
from .safety import SafetyGovernor

class AutonomousTrainer:
    def __init__(self, kernel, runtime, memory, config_manager):
        # ... existing initialization ...
        self.code_model = CodeModel(Path(__file__).parent.parent)
        self.code_model.load_all()
        self.improver = ImprovementGenerator(self.code_model, self.dataset, self.kernel)
        self.sandbox = Sandbox(Path(__file__).parent.parent)
        self.integration = IntegrationEngine(Path(__file__).parent.parent)
        self.evolution = EvolutionDB(Path.home() / ".helena" / "evolution.db")
        self.safety = SafetyGovernor(config_manager.get_section("training") or {})

    def start_session(self, focus_areas=None):
        # 1. Collect data (as before)
        data = self._collect_data(focus_areas)

        # 2. Generate improvement proposals
        proposals = self.improver.generate_proposals(focus_areas)

        # 3. Filter by safety
        safe_proposals = [p for p in proposals if self.safety.approve_patch(p)]

        # 4. Test each in sandbox
        valid_patches = []
        for patch in safe_proposals:
            test_result = self.sandbox.test_patch(patch)
            self.evolution.record_patch(patch, test_result, applied=False)
            if test_result['passed']:
                valid_patches.append(patch)

        # 5. Integrate and measure
        for patch in valid_patches:
            # Measure performance before
            perf_before = self._measure_performance()
            if self.integration.apply_patch(patch):
                # After integration, reload modules (requires restart or hot-reload)
                self._reload_modules()
                perf_after = self._measure_performance()
                self.evolution.record_patch(patch, {'passed': True}, applied=True,
                                            perf_before=perf_before, perf_after=perf_after)
                logger.info("AutonomousTrainer", f"Applied patch: {patch['id']}")