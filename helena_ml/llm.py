"""
LLM integration for HELENA with Ollama support (primary) and llama-cpp-python fallback
"""
import os
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading

from helena_core.utils.logging import get_logger

logger = get_logger()

class OllamaLLM:
    """Fast LLM integration using Ollama (local service)."""
    
    def __init__(self, model: str = "mistral", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.available = self._check_availability()
        if self.available:
            logger.info("LLM", f"Ollama available - using model: {model}")
        else:
            logger.warning("LLM", "Ollama not available. Make sure Ollama is running: ollama serve")
    
    def _check_availability(self) -> bool:
        """Check if Ollama service is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=1)
            return response.status_code == 200
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                requests.exceptions.RequestException):
            return False
    
    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
        """Generate using Ollama service - fast and non-blocking."""
        if not self.available:
            return None
        
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                },
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()
            else:
                logger.error("LLM", f"Ollama error: {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            logger.error("LLM", "Ollama request timeout")
            return None
        except Exception as e:
            logger.error("LLM", f"Ollama generation error: {e}")
            return None

class LocalLLM:
    """Wrapper for a local GGUF model using llama-cpp-python with GPU acceleration."""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_path = model_path or self._find_model()
        self.loading = False
        
        if self.model_path:
            # Load model eagerly at startup (blocking, but worth it for GPU acceleration)
            self._load_model()
        else:
            logger.warning("LLM", "No GGUF model found.")
    
    def _find_model(self) -> Optional[str]:
        """Search for a .gguf file in the models directory."""
        models_dir = Path(__file__).parent.parent / "models"
        if not models_dir.exists():
            return None
        gguf_files = list(models_dir.glob("*.gguf"))
        if gguf_files:
            return str(gguf_files[0])
        return None
    
    def _load_model(self):
        """Load model with GPU acceleration enabled."""
        try:
            from llama_cpp import Llama
            logger.info("LLM", f"Loading GGUF model with GPU acceleration: {self.model_path}")
            
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=1024,            # Context window
                n_threads=2,           # Reduced since GPU handles computation
                n_gpu_layers=33,       # Load all/most layers on GPU (NVIDIA 4050)
                verbose=False,
                n_batch=512            # Batch size for GPU
            )
            logger.info("LLM", "✓ GGUF model loaded successfully with GPU acceleration")
        except Exception as e:
            logger.error("LLM", f"Failed to load GGUF model: {e}")
            self.model = None
    
    def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7) -> str:
        """Generate using local GGUF model - fast with GPU acceleration."""
        if not self.model:
            return None
        
        try:
            output = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                echo=False,
                stop=["</s>", "User:", "\n"],
                top_p=0.9
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            logger.error("LLM", f"GGUF generation error: {e}")
            return None

class SimpleFallbackLLM:
    """Ultra-fast fallback LLM using simple pattern matching - instant responses."""
    
    def __init__(self):
        self.responses = {
            "hello": "Hello! I'm HELENA. How can I help you?",
            "hi": "Hi there! What can I do for you?",
            "how are you": "I'm functioning well, thank you for asking!",
            "help": "I can assist with various tasks. What do you need?",
            "status": "All systems operational.",
            "time": "I don't have real-time data, but I can help with other things.",
            "what is": "I can explain many concepts. Be more specific?",
            "default": "I understand. How can I help further?"
        }
    
    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
        """Instant pattern-matched response."""
        prompt_lower = prompt.lower()
        
        # Check for keyword matches
        for key, response in self.responses.items():
            if key in prompt_lower:
                return response
        
        # Default response
        return self.responses["default"]

class HybridLLM:
    """Hybrid LLM that tries Ollama first, then local GGUF with GPU, then simple fallback."""
    
    def __init__(self):
        # Try Ollama first (fast service)
        self.ollama = OllamaLLM()
        # Initialize local GGUF with GPU acceleration (eager loading at startup)
        self.local = LocalLLM()
        # Ultra-fast fallback
        self.simple = SimpleFallbackLLM()
        
        if self.ollama.available:
            logger.info("LLM", "✓ Using Ollama (fastest)")
        elif self.local.model:
            logger.info("LLM", "✓ Using GGUF with GPU acceleration (NVIDIA 4050)")
        else:
            logger.info("LLM", "⚠ Using simple pattern-based fallback")
    
    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
        """Generate response using the best available backend."""
        # Try Ollama first if available
        if self.ollama.available:
            result = self.ollama.generate(prompt, max_tokens, temperature)
            if result:
                return result
        
        # Try local GGUF with GPU (should be loaded and fast now)
        if self.local.model:
            result = self.local.generate(prompt, max_tokens, temperature)
            if result:
                return result
        
        # Fall back to simple pattern matching (instant)
        return self.simple.generate(prompt, max_tokens, temperature)
