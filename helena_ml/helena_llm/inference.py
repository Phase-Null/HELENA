"""
HELENA-Net Inference Engine
 
Fast generation using:
- Streaming token-by-token generation with persistent membrane state
- KV-cache equivalent: SSM state is carried between tokens (O(1) memory)
- Top-p + top-k sampling
- Repetition penalty
- Batch generation support
"""
import time
import torch
import torch.nn.functional as F
from typing import List, Dict, Optional, Iterator
from pathlib import Path
 
from .config import HelenaNetConfig
from .architecture import HelenaNet
from .tokenizer import HelenaTokenizer
 
 
class HelenaNetInference:
    """
    Inference wrapper for HELENA-Net.
 
    Designed to slot into HybridLLM as a drop-in replacement for OllamaLLM.
    Implements the same .chat() and .generate() interface.
    """
 
    def __init__(self, model_path: str, device: Optional[str] = None):
        self.model_path = Path(model_path)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[HelenaNet] = None
        self.tokenizer: Optional[HelenaTokenizer] = None
        self.config: Optional[HelenaNetConfig] = None
        self.available = False
        self._load()
 
    def _load(self) -> None:
        """Load model and tokenizer from disk."""
        try:
            config_path = self.model_path / "config.pt"
            model_path = self.model_path / "model.pt"
            tok_path = self.model_path / "tokenizer"
 
            if not model_path.exists():
                print(f"HELENA-Net: No model found at {model_path}. "
                      f"Train first with: python -m helena_ml.helena_llm.train")
                return
 
            # Load config
            if config_path.exists():
                self.config = torch.load(config_path, map_location=self.device, weights_only=False)
            else:
                from .config import HELENA_NANO
                print("HELENA-Net: config.pt missing, defaulting to NANO config.")
                self.config = HELENA_NANO
 
            # Load model
            self.model = HelenaNet(self.config)
            state = torch.load(model_path, map_location=self.device, weights_only=False)
            self.model.load_state_dict(state)
            self.model.eval()
            self.model.to(self.device)
 
            # Load tokenizer
            self.tokenizer = HelenaTokenizer.load(str(tok_path))
 
            self.available = True
            params = self.model.get_num_params()
            active = self.model.get_active_params_per_token()
            print(f"HELENA-Net loaded: {params/1e6:.1f}M total params, "
                  f"{active/1e6:.1f}M active per token | device: {self.device}")
 
        except Exception as e:
            print(f"HELENA-Net load failed: {e}")
            self.available = False
 
    # ── Public API (matches OllamaLLM interface) ──────────────────
 
    def chat(self, messages: List[Dict[str, str]],
             max_tokens: int = 512,
             temperature: float = 0.7) -> Optional[str]:
        """
        Generate response from conversation messages.
        Compatible with HybridLLM.chat() interface.
        """
        if not self.available:
            return None
        try:
            input_ids = self.tokenizer.encode_conversation(messages)
            max_input = self.config.max_seq_len - min(max_tokens, self.config.max_new_tokens) - 10
            input_ids = input_ids[-max_input:]
            response_ids = self._generate(
                input_ids,
                max_new_tokens=min(max_tokens, self.config.max_new_tokens),
                temperature=temperature,
            )
            # Decode only the new tokens
            new_ids = response_ids[len(input_ids):]
            return self.tokenizer.decode(new_ids, skip_special_tokens=True)
        except Exception as e:
            print(f"HELENA-Net chat error: {e}")
            return None
 
    def generate(self, prompt: str,
                 max_tokens: int = 512,
                 temperature: float = 0.7) -> Optional[str]:
        """
        Generate from flat prompt string.
        Compatible with HybridLLM.generate() interface.
        """
        if not self.available:
            return None
        try:
            input_ids = self.tokenizer.encode(prompt, add_special_tokens=True)
            max_input = self.config.max_seq_len - min(max_tokens, self.config.max_new_tokens) - 10
            input_ids = input_ids[-max_input:]
            response_ids = self._generate(
                input_ids,
                max_new_tokens=min(max_tokens, self.config.max_new_tokens),
                temperature=temperature,
            )
            new_ids = response_ids[len(input_ids):]
            return self.tokenizer.decode(new_ids, skip_special_tokens=True)
        except Exception as e:
            print(f"HELENA-Net generate error: {e}")
            return None
 
    def stream(self, messages: List[Dict[str, str]],
               temperature: float = 0.7) -> Iterator[str]:
        """
        Stream tokens one by one as they're generated.
        For future streaming UI support.
        """
        if not self.available:
            return
        input_ids = self.tokenizer.encode_conversation(messages)
        max_input = self.config.max_seq_len - self.config.max_new_tokens - 10
        input_ids = input_ids[-max_input:]
        for token_id in self._generate_stream(input_ids, temperature=temperature):
            token = self.tokenizer.decode([token_id], skip_special_tokens=True)
            if token:
                yield token
 
    # ── Core generation ───────────────────────────────────────────
 
    @torch.no_grad()
    def _generate(self, input_ids: List[int],
                  max_new_tokens: int = 512,
                  temperature: float = 0.7) -> List[int]:
        """
        Autoregressive generation with SSM state persistence.
 
        Key advantage over transformers:
        - The SSM state h(t) acts as the "KV cache"
        - It's fixed size regardless of sequence length
        - Generating token 1000 costs the same as token 1
        """
        device = self.device
        ids = torch.tensor([input_ids], dtype=torch.long, device=device)
 
        # Process prompt: get SSM states and logits for last position
        membranes = None
        with torch.no_grad():
            logits, _, membranes = self.model(ids, membranes=membranes)
 
        # Generate new tokens one by one
        # SSM state (membranes) is maintained — O(1) memory per new token
        generated = list(input_ids)
        past_ids = set(input_ids[-50:])  # for repetition penalty
 
        eos_id = self.tokenizer.SPECIAL_TOKENS["<eos>"]
 
        for _ in range(max_new_tokens):
            # Only feed the last generated token
            last_token = torch.tensor([[generated[-1]]], dtype=torch.long, device=device)
            logits, _, membranes = self.model(last_token, membranes=membranes)
            next_logits = logits[0, -1, :]  # [vocab_size]
 
            # Repetition penalty
            if self.config.repetition_penalty != 1.0:
                for tid in past_ids:
                    if tid < next_logits.shape[0]:
                        if next_logits[tid] > 0:
                            next_logits[tid] /= self.config.repetition_penalty
                        else:
                            next_logits[tid] *= self.config.repetition_penalty
 
            # Sample next token
            next_id = self._sample(next_logits, temperature,
                                   self.config.top_p, self.config.top_k)
            generated.append(next_id)
            past_ids.add(next_id)
 
            if next_id == eos_id:
                break
 
        return generated
 
    @torch.no_grad()
    def _generate_stream(self, input_ids: List[int],
                         temperature: float = 0.7) -> Iterator[int]:
        """Stream token IDs one by one."""
        device = self.device
        ids = torch.tensor([input_ids], dtype=torch.long, device=device)
        logits, _, membranes = self.model(ids)
        generated = list(input_ids)
        eos_id = self.tokenizer.SPECIAL_TOKENS["<eos>"]
 
        for _ in range(self.config.max_new_tokens):
            last_token = torch.tensor([[generated[-1]]], dtype=torch.long, device=device)
            logits, _, membranes = self.model(last_token, membranes=membranes)
            next_logits = logits[0, -1, :]
            next_id = self._sample(next_logits, temperature,
                                   self.config.top_p, self.config.top_k)
            generated.append(next_id)
            yield next_id
            if next_id == eos_id:
                break
 
    def _sample(self, logits: torch.Tensor, temperature: float,
                top_p: float, top_k: int) -> int:
        """Sample next token with temperature, top-p, and top-k filtering."""
        if temperature == 0.0:
            return logits.argmax().item()
 
        logits = logits / temperature
 
        # Top-k filtering
        if top_k > 0:
            top_k = min(top_k, logits.shape[-1])
            threshold = logits.topk(top_k).values[-1]
            logits = logits.masked_fill(logits < threshold, float("-inf"))
 
        # Top-p (nucleus) filtering
        if top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
            # Remove tokens with cumulative prob above threshold
            sorted_indices_to_remove = cumulative_probs - F.softmax(sorted_logits, dim=-1) > top_p
            sorted_logits[sorted_indices_to_remove] = float("-inf")
            # Scatter back
            logits = torch.zeros_like(logits).scatter_(0, sorted_indices, sorted_logits)
 
        probs = F.softmax(logits, dim=-1)
        return torch.multinomial(probs, num_samples=1).item()
 
    # ── Benchmarking ──────────────────────────────────────────────
 
    def benchmark(self, n_tokens: int = 100) -> Dict:
        """Measure tokens per second."""
        if not self.available:
            return {"error": "Model not loaded"}
 
        prompt = "Hello HELENA. Tell me about yourself."
        input_ids = self.tokenizer.encode(prompt)
 
        start = time.perf_counter()
        result = self._generate(input_ids, max_new_tokens=n_tokens, temperature=0.7)
        elapsed = time.perf_counter() - start
 
        new_tokens = len(result) - len(input_ids)
        tps = new_tokens / elapsed if elapsed > 0 else 0
 
        return {
            "tokens_generated": new_tokens,
            "time_seconds": round(elapsed, 3),
            "tokens_per_second": round(tps, 1),
            "ms_per_token": round(1000 / tps if tps > 0 else 0, 1),
            "device": self.device,
        }
 
