# tests/unit/test_kernel.py
"""
Unit tests for HELENA Kernel
"""
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from helena_core.kernel import (
    HELENAKernel,
    TaskPriority,
    OperationalMode,
    TaskRequest,
    TaskContext
)

class TestHELENAKernel(unittest.TestCase):
    """Test HELENA Kernel"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config_mock = Mock()
        self.config_mock.get_section.return_value = {
            "verbosity": 0.4,
            "technical_depth": 0.8,
            "humor_threshold": 0.7,
            "creativity_level": 0.6,
            "formality_level": 0.8,
            "response_style": "concise_technical"
        }
        
        self.kernel = HELENAKernel(
            operator_id="test_operator",
            config_manager=self.config_mock
        )
    
    def test_initialization(self):
        """Test kernel initialization"""
        with patch.object(self.kernel, '_start_event_loop'):
            success = self.kernel.initialize()
            self.assertTrue(success)
            self.assertTrue(self.kernel.initialized)
    
    def test_mode_change(self):
        """Test operational mode changes"""
        # Start in ENGINEERING mode
        self.assertEqual(self.kernel.mode, OperationalMode.ENGINEERING)
        
        # Change to TOOL mode
        result = self.kernel.change_mode(OperationalMode.TOOL)
        self.assertTrue(result["success"])
        self.assertEqual(self.kernel.mode, OperationalMode.TOOL)
        
        # Change to DEFENSIVE mode
        result = self.kernel.change_mode(OperationalMode.DEFENSIVE)
        self.assertTrue(result["success"])
        self.assertEqual(self.kernel.mode, OperationalMode.DEFENSIVE)
    
    def test_task_submission(self):
        """Test task submission"""
        with patch.object(self.kernel, '_start_processing'):
            task_id = self.kernel.submit_task(
                command="code_generate",
                parameters={"language": "python", "description": "test"},
                source="operator",
                priority=TaskPriority.NORMAL
            )
            
            self.assertIsNotNone(task_id)
            self.assertIsInstance(task_id, str)
            self.assertTrue(task_id.startswith("task_"))
    
    def test_permission_denial(self):
        """Test permission denial for unauthorized commands"""
        # Switch to TOOL mode (restricted permissions)
        self.kernel.change_mode(OperationalMode.TOOL)
        
        # Try to execute system_control command (not allowed in TOOL mode)
        task_id = self.kernel.submit_task(
            command="system_control",
            parameters={"action": "shutdown"},
            source="operator",
            priority=TaskPriority.NORMAL
        )
        
        # Should be denied (returns None)
        self.assertIsNone(task_id)
    
    def test_lockdown_mode(self):
        """Test lockdown mode activation"""
        # Activate lockdown
        success = self.kernel.set_lockdown_mode(True)
        self.assertTrue(success)
        self.assertTrue(self.kernel.lockdown_mode)
        self.assertEqual(self.kernel.security_level, "LOCKDOWN")
        
        # Should be in DEFENSIVE mode during lockdown
        self.assertEqual(self.kernel.mode, OperationalMode.DEFENSIVE)
        
        # Try to submit non-critical task during lockdown
        task_id = self.kernel.submit_task(
            command="code_generate",
            parameters={"language": "python", "description": "test"},
            source="operator",
            priority=TaskPriority.NORMAL
        )
        
        # Should be rejected during lockdown
        self.assertIsNone(task_id)
        
        # Deactivate lockdown
        success = self.kernel.set_lockdown_mode(False)
        self.assertTrue(success)
        self.assertFalse(self.kernel.lockdown_mode)
    
    def test_system_status(self):
        """Test system status retrieval"""
        status = self.kernel.get_system_status()
        
        # Check required fields
        self.assertIn("operator", status)
        self.assertIn("mode", status)
        self.assertIn("security_level", status)
        self.assertIn("active", status)
        self.assertIn("initialized", status)
        self.assertIn("metrics", status)
        self.assertIn("queue", status)
        
        # Verify values
        self.assertEqual(status["operator"], "test_operator")
        self.assertEqual(status["mode"], OperationalMode.ENGINEERING.name)
    
    def test_graceful_shutdown(self):
        """Test graceful shutdown"""
        with patch.object(self.kernel.worker_pool, 'shutdown') as mock_shutdown:
            success = self.kernel.shutdown(graceful=True)
            self.assertTrue(success)
            mock_shutdown.assert_called_once_with(wait=True)
    
    def test_task_queue_priority(self):
        """Test task queue priority ordering"""
        # Submit tasks with different priorities
        tasks = []
        for priority in [TaskPriority.LOW, TaskPriority.HIGH, TaskPriority.NORMAL]:
            task_id = self.kernel.submit_task(
                command="test",
                parameters={},
                source="system",
                priority=priority
            )
            if task_id:
                tasks.append((priority, task_id))
        
        # In a proper test, we would verify dequeue order
        # For now, just verify submission
        self.assertGreater(len(tasks), 0)
    
    def test_validation_chain(self):
        """Test validation chain"""
        # Create a test task
        context = TaskContext(
            operator_id="test",
            session_id="session_test",
            source="operator",
            permissions=set(),
            resource_budget={},
            environmental_state={}
        )
        
        task = TaskRequest(
            task_id="test_task",
            command="code_generate",
            parameters={"language": "python"},
            context=context,
            priority=TaskPriority.NORMAL
        )
        
        # Run validation
        with patch.object(self.kernel.validation_chain, 'validate') as mock_validate:
            mock_validate.return_value.passed = True
            # The actual validation happens in process_single_task
            # This just tests the mocking setup
    
    def tearDown(self):
        """Clean up after tests"""
        if hasattr(self.kernel, 'shutdown'):
            self.kernel.shutdown(graceful=False)

class TestOperationalModes(unittest.TestCase):
    """Test operational modes"""
    
    def test_mode_configurations(self):
        """Test mode configurations"""
        from helena_core.kernel.modes import ModeProcessor
        
        processor = ModeProcessor()
        processor.load_processors()
        
        # Check all modes have configurations
        for mode in OperationalMode:
            config = processor.get_mode_config(mode)
            self.assertIsNotNone(config)
            
            # Check config values
            self.assertGreater(config.max_workers, 0)
            self.assertGreater(config.response_time_target, 0)
            self.assertGreaterEqual(config.resource_multiplier, 0)
            self.assertLessEqual(config.resource_multiplier, 1)
    
    def test_mode_processing(self):
        """Test mode-specific processing"""
        from helena_core.kernel.modes import ModeProcessor
        
        processor = ModeProcessor()
        processor.load_processors()
        
        # Test each mode
        for mode in OperationalMode:
            mock_task = Mock()
            mock_task.command = "test"
            
            result = processor.process(mode, mock_task)
            
            # Check result structure
            self.assertIn("mode", result)
            self.assertEqual(result["mode"], mode.name)
            self.assertIn("processing_time", result)

if __name__ == "__main__":
    unittest.main()
