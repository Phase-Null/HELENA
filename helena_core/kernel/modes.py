# helena_core/kernel/modes.py
"""
Operational modes and their processing pipelines
"""
from enum import Enum, auto
from typing import Dict, Any, Optional, Callable, List
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class OperationalMode(Enum):
    """HELENA's operational modes"""
    ENGINEERING = auto()    # Full capabilities, verbose output
    TOOL = auto()           # Minimal output, execution focused
    DEFENSIVE = auto()      # High-speed, security focused
    BACKGROUND = auto()     # Low-resource, gaming compatible

@dataclass
class ModeConfig:
    """Configuration for an operational mode"""
    max_workers: int
    response_time_target: float  # seconds
    resource_multiplier: float  # 0.0-1.0
    personality_enabled: bool
    validation_strictness: int  # 1-3
    learning_enabled: bool

class ModeProcessor:
    """Process tasks according to current operational mode"""
    
    def __init__(self, kernel=None):
        self.kernel = kernel
        self.processors: Dict[OperationalMode, Callable] = {}
        self.configs: Dict[OperationalMode, ModeConfig] = {}
        
    def load_processors(self):
        """Load mode-specific processors"""
        self.processors = {
            OperationalMode.ENGINEERING: self._process_engineering,
            OperationalMode.TOOL: self._process_tool,
            OperationalMode.DEFENSIVE: self._process_defensive,
            OperationalMode.BACKGROUND: self._process_background,
        }
        
        # Load configurations
        self.configs = {
            OperationalMode.ENGINEERING: ModeConfig(
                max_workers=4,
                response_time_target=2.0,
                resource_multiplier=0.7,
                personality_enabled=True,
                validation_strictness=3,
                learning_enabled=True
            ),
            OperationalMode.TOOL: ModeConfig(
                max_workers=2,
                response_time_target=1.0,
                resource_multiplier=0.3,
                personality_enabled=False,
                validation_strictness=2,
                learning_enabled=False
            ),
            OperationalMode.DEFENSIVE: ModeConfig(
                max_workers=8,
                response_time_target=0.5,
                resource_multiplier=1.0,
                personality_enabled=False,
                validation_strictness=3,
                learning_enabled=False
            ),
            OperationalMode.BACKGROUND: ModeConfig(
                max_workers=1,
                response_time_target=5.0,
                resource_multiplier=0.1,
                personality_enabled=False,
                validation_strictness=1,
                learning_enabled=True
            )
        }
        
        logger.info("ModeProcessor", "Mode processors loaded")
    
    def process(self, mode: OperationalMode, task) -> Dict[str, Any]:
        """Process task according to mode"""
        processor = self.processors.get(mode)
        if not processor:
            logger.error("ModeProcessor", f"No processor for mode: {mode}")
            return {"error": f"Unsupported mode: {mode}"}
        
        start_time = time.time()
        
        try:
            result = processor(task)
            processing_time = time.time() - start_time
            
            # Add processing metadata
            result["processing_time"] = processing_time
            result["mode"] = mode.name
            
            # Check response time target
            config = self.configs.get(mode)
            if config and processing_time > config.response_time_target:
                result["performance_warning"] = f"Slow response: {processing_time:.2f}s"
            
            return result
            
        except Exception as e:
            logger.error("ModeProcessor", f"Mode processing failed: {e}")
            return {
                "error": str(e),
                "mode": mode.name,
                "processing_time": time.time() - start_time
            }
    
    def _process_engineering(self, task) -> Dict[str, Any]:
        """Engineering mode - comprehensive analysis and verbose output"""
        command = task.command
        
        # Handle chat command using LLM if available
        if command == "chat":
            message = task.parameters.get("message", "")
            # Check if kernel has LLM attached
            llm = self.kernel.llm if self.kernel and hasattr(self.kernel, 'llm') else None
            if llm:
                # Generate response
                response = llm.generate(prompt=f"User: {message}\nAssistant:", max_tokens=200, temperature=0.7)
                
                if response:
                    return {
                        "result": response,
                        "processing_time": 0.1,
                        "details_level": "high"
                    }
                else:
                    return {
                        "result": f"Received: {message}",
                        "processing_time": 0.1,
                        "details_level": "high"
                    }
            else:
                return {
                    "result": f"Received: {message} (LLM not initialized)",
                    "processing_time": 0.1,
                    "details_level": "high"
                }
        
        # Existing analysis pipeline for other commands
        analysis = self._analyze_task_engineering(task)
        solutions = self._generate_solutions(analysis)
        evaluation = self._evaluate_solutions(solutions)
        recommendation = self._select_recommendation(evaluation)
        
        return {
            "analysis": analysis,
            "solutions": solutions,
            "evaluation": evaluation,
            "recommendation": recommendation,
            "confidence": self._calculate_confidence(evaluation),
            "details_level": "high"
        }

    def _process_tool(self, task) -> Dict[str, Any]:
        """Tool mode - minimal output, direct execution"""
        # Direct execution path
        result = self._execute_directly(task)
        
        return {
            "result": result,
            "success": True if result else False,
            "details_level": "minimal"
        }
    
    def _process_defensive(self, task) -> Dict[str, Any]:
        """Defensive mode - security focused, rapid response"""
        # Security-first processing
        security_check = self._security_scan(task)
        if not security_check["passed"]:
            return {
                "error": "Security check failed",
                "security_issues": security_check["issues"],
                "action": "blocked",
                "details_level": "security"
            }
        
        # Rapid execution with monitoring
        result = self._execute_with_monitoring(task)
        
        return {
            "result": result,
            "security_check": security_check,
            "monitoring": self._get_monitoring_data(),
            "details_level": "security"
        }
    
    def _process_background(self, task) -> Dict[str, Any]:
        """Background mode - low priority, resource efficient"""
        # Simplified processing for background tasks
        if self._should_defer_task(task):
            return {
                "deferred": True,
                "reason": "Low priority background task",
                "scheduled_time": time.time() + 300,  # 5 minutes
                "details_level": "minimal"
            }
        
        # Efficient execution
        result = self._execute_efficiently(task)
        
        return {
            "result": result,
            "efficiency_metrics": self._calculate_efficiency(),
            "details_level": "minimal"
        }
    
    # Helper methods (would be fully implemented in production)
    def _analyze_task_engineering(self, task) -> Dict[str, Any]:
        return {"complexity": "medium", "type": task.command}
    
    def _generate_solutions(self, analysis) -> List[Dict[str, Any]]:
        return [{"approach": "standard", "steps": 3}]
    
    def _evaluate_solutions(self, solutions) -> Dict[str, Any]:
        return {"best_solution": 0, "scores": [0.8]}
    
    def _select_recommendation(self, evaluation) -> Dict[str, Any]:
        return {"action": "proceed", "steps": ["Execute standard approach"]}
    
    def _calculate_confidence(self, evaluation) -> float:
        return 0.85
    
    def _execute_directly(self, task):
        return {"executed": task.command}
    
    def _security_scan(self, task) -> Dict[str, Any]:
        return {"passed": True, "issues": []}
    
    def _execute_with_monitoring(self, task):
        return {"executed": task.command, "monitored": True}
    
    def _get_monitoring_data(self):
        return {"active": True, "checks": 3}
    
    def _should_defer_task(self, task) -> bool:
        return False  # Simplified
    
    def _execute_efficiently(self, task):
        return {"executed": task.command, "efficient": True}
    
    def _calculate_efficiency(self):
        return {"cpu_usage": 0.1, "memory_usage": 0.05}
    
    def get_mode_config(self, mode: OperationalMode) -> Optional[ModeConfig]:
        """Get configuration for a mode"""
        return self.configs.get(mode)
    
    def update_mode_config(self, mode: OperationalMode, **kwargs):
        """Update mode configuration"""
        if mode in self.configs:
            config = self.configs[mode]
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            logger.info("ModeProcessor", f"Updated config for mode: {mode.name}")
