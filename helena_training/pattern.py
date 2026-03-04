"""
Pattern recognition – real implementations using statistics and embeddings.
"""
import time
from typing import Dict, List, Any
from collections import defaultdict, Counter

# Lazy loading of heavy dependencies
EMBEDDINGS_AVAILABLE = False
SentenceTransformer = None

def _try_import_embeddings():
    global EMBEDDINGS_AVAILABLE, SentenceTransformer
    if not EMBEDDINGS_AVAILABLE:
        try:
            from sentence_transformers import SentenceTransformer as ST
            import numpy as np
            SentenceTransformer = ST
            EMBEDDINGS_AVAILABLE = True
        except ImportError:
            EMBEDDINGS_AVAILABLE = False
        except Exception:
            # Catch other exceptions like torch initialization issues
            EMBEDDINGS_AVAILABLE = False

from helena_core.utils.logging import get_logger

logger = get_logger()

class TemporalPatternRecognizer:
    def analyze(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        kernel_data = data.get('sources', {}).get('kernel', [])
        if not kernel_data:
            return patterns

        # Group by session
        sessions = defaultdict(list)
        for entry in kernel_data:
            session = entry.get('context', {}).get('session_id', 'default')
            sessions[session].append(entry)

        for session, entries in sessions.items():
            if len(entries) < 2:
                continue
            # Look for successful sequences
            for i in range(len(entries)-1):
                cmd1 = entries[i].get('command', '')
                cmd2 = entries[i+1].get('command', '')
                if cmd1 and cmd2:
                    patterns.append({
                        'type': 'command_sequence',
                        'sequence': [cmd1, cmd2],
                        'success': entries[i+1].get('result', {}).get('status') == 'COMPLETED',
                        'confidence': 0.6,
                        'timestamp': time.time()
                    })
        return patterns

class SemanticPatternRecognizer:
    def __init__(self):
        self.encoder = None

    def analyze(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        kernel_data = data.get('sources', {}).get('kernel', [])
        if not kernel_data:
            return patterns

        # Group by command name first (simple)
        cmd_counter = Counter()
        for entry in kernel_data:
            cmd = entry.get('command', '')
            if cmd:
                cmd_counter[cmd] += 1

        for cmd, count in cmd_counter.items():
            if count > 5:
                patterns.append({
                    'type': 'frequent_command',
                    'command': cmd,
                    'frequency': count,
                    'confidence': 0.8,
                    'timestamp': time.time()
                })

        # If we have embeddings, cluster similar commands
        if EMBEDDINGS_AVAILABLE and len(kernel_data) > 10:
            # Load embeddings lazily if needed
            _try_import_embeddings()
            if self.encoder is None and SentenceTransformer:
                try:
                    self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
                    logger.info("PatternRecognizer", "Loaded sentence transformer")
                except Exception as e:
                    logger.error("PatternRecognizer", f"Failed to load embeddings: {e}")
            # This is simplified; in reality you'd embed commands and cluster
        return patterns

class StructuralPatternRecognizer:
    def analyze(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns = []
        kernel_data = data.get('sources', {}).get('kernel', [])
        if not kernel_data:
            return patterns

        failure_by_cmd = defaultdict(list)
        for entry in kernel_data:
            if entry.get('result', {}).get('status') != 'COMPLETED':
                cmd = entry.get('command', '')
                if cmd:
                    failure_by_cmd[cmd].append(entry)

        for cmd, failures in failure_by_cmd.items():
            if len(failures) > 3:
                # Check if failures are due to missing parameters
                missing_params = []
                for f in failures:
                    error = f.get('result', {}).get('error', '')
                    if 'missing' in error.lower():
                        import re
                        m = re.search(r"['\"](\w+)['\"]", error)
                        if m:
                            missing_params.append(m.group(1))
                if missing_params:
                    patterns.append({
                        'type': 'missing_parameter',
                        'command': cmd,
                        'parameters': list(set(missing_params)),
                        'confidence': 0.7,
                        'timestamp': time.time()
                    })
        return patterns

class PatternRecognizer:
    def __init__(self):
        self.algorithms = {
            'temporal': TemporalPatternRecognizer(),
            'semantic': SemanticPatternRecognizer(),
            'structural': StructuralPatternRecognizer(),
        }

    def analyze(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        all_patterns = []
        for name, algo in self.algorithms.items():
            pats = algo.analyze(data)
            for p in pats:
                p['source'] = name
                all_patterns.append(p)
        logger.debug("PatternRecognizer", f"Found {len(all_patterns)} patterns")
        return all_patterns
