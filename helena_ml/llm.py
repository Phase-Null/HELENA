"""
LLM integration for HELENA.
 
Backend priority:
1. HELENA-Net (helena_ml/helena_llm/) — HELENA's own SpikingSSM-MoE model
2. Ollama (Mistral) — current primary while HELENA-Net is training
3. LocalLLM (GGUF via llama-cpp-python) — GPU-accelerated fallback
4. SimpleFallback — pattern-matched instant responses
 
When HELENA-Net is trained and saved to helena_memory/helena_net/,
it automatically becomes the primary backend. No other code changes needed.
"""
import os
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
 
from helena_core.utils.logging import get_logger
 
logger = get_logger()
 
 
class OllamaLLM:
    """Ollama service integration — /api/chat endpoint."""
 
    def __init__(self, model: str = "mistral", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.available = self._check_availability()
        if self.available:
            logger.info("LLM", f"Ollama available — model: {model}")
        else:
            logger.warning("LLM", "Ollama not available. Run: ollama serve")
 
    def _check_availability(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=1)
            return response.status_code == 200
        except Exception:
            return False
 
    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 50000,
             temperature: float = 0.7) -> Optional[str]:
        if not self.available:
            return None
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120,
            )
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "").strip()
            logger.error("LLM", f"Ollama error: {response.status_code}")
            return None
        except requests.exceptions.Timeout:
            logger.error("LLM", "Ollama timeout")
            return None
        except Exception as e:
            logger.error("LLM", f"Ollama error: {e}")
            return None
 
    def generate(self, prompt: str, max_tokens: int = 50000,
                 temperature: float = 0.7) -> Optional[str]:
        if not self.available:
            return None
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120,
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            return None
        except Exception as e:
            logger.error("LLM", f"Ollama generate error: {e}")
            return None
 
 
class LocalLLM:
    """Local GGUF model via llama-cpp-python with GPU acceleration."""
 
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_path = model_path or self._find_model()
        if self.model_path:
            self._load_model()
        else:
            logger.warning("LLM", "No GGUF model found.")
 
    def _find_model(self) -> Optional[str]:
        models_dir = Path(__file__).parent.parent / "models"
        if not models_dir.exists():
            return None
        gguf_files = list(models_dir.glob("*.gguf"))
        return str(gguf_files[0]) if gguf_files else None
 
    def _load_model(self):
        try:
            from llama_cpp import Llama
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=1024, n_threads=2, n_gpu_layers=33,
                verbose=False, n_batch=512,
            )
            logger.info("LLM", "GGUF model loaded with GPU acceleration")
        except Exception as e:
            logger.error("LLM", f"GGUF load failed: {e}")
            self.model = None
 
    def generate(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> Optional[str]:
        if not self.model:
            return None
        try:
            output = self.model(
                prompt, max_tokens=max_tokens, temperature=temperature,
                echo=False, stop=["</s>", "User:", "\n"], top_p=0.9,
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            logger.error("LLM", f"GGUF error: {e}")
            return None
 
 
class SimpleFallbackLLM:
    """Instant pattern-matched fallback."""
 
    RESPONSES = {
        "hello": "Hello! I'm HELENA. How can I help you?",
        "hi": "Hi there! What can I do for you?",
        "how are you": "I'm functioning well, thank you.",
        "help": "I can assist with various tasks. What do you need?",
        "status": "All systems operational.",
        "default": "I understand. How can I help further?",
    }
 
    def generate(self, prompt: str, **kwargs) -> str:
        pl = prompt.lower()
        for key, resp in self.RESPONSES.items():
            if key in pl:
                return resp
        return self.RESPONSES["default"]
 
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        last = next((m["content"] for m in reversed(messages)
                     if m["role"] == "user"), "")
        return self.generate(last)
 
 
class HybridLLM:
    """
    Hybrid LLM backend chain.
 
    Priority:
    1. HELENA-Net (own model) — when trained and available
    2. Ollama (Mistral) — current primary
    3. LocalLLM (GGUF) — GPU fallback
    4. SimpleFallback — instant patterns
 
    To activate HELENA-Net: train it with
        python -m helena_ml.helena_llm.train --config nano
    The model saves to helena_memory/helena_net/ and is auto-detected here.
    """
 
    def __init__(self):
        # Try HELENA-Net first
        self.helena_net = self._try_load_helena_net()
 
        # Always init Ollama as primary fallback
        self.ollama = OllamaLLM()
 
        # Local GGUF
        self.local = LocalLLM()
 
        # Instant fallback
        self.simple = SimpleFallbackLLM()
 
        # Report active backend
        if self.helena_net and self.helena_net.available:
            logger.info("LLM", "✓ HELENA-Net active (own model — primary)")
        elif self.ollama.available:
            logger.info("LLM", "✓ Ollama active (Mistral)")
        elif self.local.model:
            logger.info("LLM", "✓ GGUF active (GPU)")
        else:
            logger.info("LLM", "⚠ SimpleFallback active")
 
    def _try_load_helena_net(self):
        """Attempt to load HELENA's own model."""
        try:
            model_path = Path(__file__).parent.parent / "helena_memory" / "helena_net"
            if not (model_path / "model.pt").exists():
                return None
            from helena_ml.helena_llm import HelenaNetInference
            net = HelenaNetInference(str(model_path))
            return net if net.available else None
        except Exception as e:
            logger.warning("LLM", f"HELENA-Net not available: {e}")
            return None
 
    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 50000,
             temperature: float = 0.7) -> Optional[str]:
        """Generate from message list — preferred interface."""
        # HELENA-Net first
        if self.helena_net and self.helena_net.available:
            result = self.helena_net.chat(messages, max_tokens=max_tokens,
                                          temperature=temperature)
            if result:
                return result
 
        # Ollama
        if self.ollama.available:
            result = self.ollama.chat(messages, max_tokens, temperature)
            if result:
                return result
 
        # Fallback: extract last user message for non-chat backends
        last_user = next((m["content"] for m in reversed(messages)
                         if m["role"] == "user"), "")
        return self.generate(last_user, max_tokens, temperature)
 
    def generate(self, prompt: str, max_tokens: int = 50000,
                 temperature: float = 0.7) -> Optional[str]:
        """Generate from flat prompt string."""
        if self.helena_net and self.helena_net.available:
            result = self.helena_net.generate(prompt, max_tokens, temperature)
            if result:
                return result
 
        if self.ollama.available:
            result = self.ollama.generate(prompt, max_tokens, temperature)
            if result:
                return result
 
        if self.local.model:
            result = self.local.generate(prompt, max_tokens, temperature)
            if result:
                return result
 
        return self.simple.generate(prompt)
 
