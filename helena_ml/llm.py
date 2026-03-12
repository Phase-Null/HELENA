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
    
    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 50000, temperature: float = 0.7) -> Optional[str]:
        """Generate using Ollama /api/chat endpoint with proper message list."""
        if not self.available:
            return None
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                },
                timeout=120
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("message", {}).get("content", "").strip()
            else:
                logger.error("LLM", f"Ollama chat error: {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            logger.error("LLM", "Ollama chat request timeout")
            return None
        except Exception as e:
            logger.error("LLM", f"Ollama chat error: {e}")
            return None

    def generate(self, prompt: str, max_tokens: int = 50000, temperature: float = 0.7) -> Optional[str]:
        """Generate using Ollama /api/generate - fallback for flat prompts."""
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
                timeout=120
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
                n_ctx=1024,
                n_threads=2,
                n_gpu_layers=33,
                verbose=False,
                n_batch=512
            )
            logger.info("LLM", "✓ GGUF model loaded successfully with GPU acceleration")
        except Exception as e:
            logger.error("LLM", f"Failed to load GGUF model: {e}")
            self.model = None
    
    def generate(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7) -> Optional[str]:
        """Generate using local GGUF model."""
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
    """Ultra-fast fallback LLM using simple pattern matching."""
    
    def __init__(self):
        self.responses = {
            "hello": "Hello! I'm HELENA. How can I help you?",
            "hi": "Hi there! What can I do for you?",
            "how are you": "I'm functioning well, thank you for asking!",
            "help": "I can assist with various tasks. What do you need?",
            "status": "All systems operational.",
            "default": "I understand. How can I help further?"
        }
    
    def generate(self, prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
        """Instant pattern-matched response."""
        prompt_lower = prompt.lower()
        for key, response in self.responses.items():
            if key in prompt_lower:
                return response
        return self.responses["default"]

class HybridLLM:
    """Hybrid LLM that tries Ollama first, then local GGUF, then simple fallback."""
    
    def __init__(self):
        self.ollama = OllamaLLM()
        self.local = LocalLLM()
        self.simple = SimpleFallbackLLM()
        
        if self.ollama.available:
            logger.info("LLM", "✓ Using Ollama (fastest)")
        elif self.local.model:
            logger.info("LLM", "✓ Using GGUF with GPU acceleration")
        else:
            logger.info("LLM", "⚠ Using simple pattern-based fallback")
    
    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 50000, temperature: float = 0.7) -> Optional[str]:
        """Generate response using structured message list (preferred)."""
        if self.ollama.available:
            result = self.ollama.chat(messages, max_tokens, temperature)
            if result:
                return result
        # LocalLLM and SimpleFallback don't support chat format — fall through to generate
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return self.generate(last_user, max_tokens, temperature)

    def generate(self, prompt: str, max_tokens: int = 50000, temperature: float = 0.7) -> Optional[str]:
        """Generate response using flat prompt string (fallback)."""
        if self.ollama.available:
            result = self.ollama.generate(prompt, max_tokens, temperature)
            if result:
                return result
        if self.local.model:
            result = self.local.generate(prompt, max_tokens, temperature)
            if result:
                return result
        return self.simple.generate(prompt, max_tokens, temperature)
