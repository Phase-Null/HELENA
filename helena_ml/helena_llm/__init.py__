"""
HELENA-Net: Spiking State Space Model with Mixture of Experts
 
HELENA's own language model — designed to replace Mistral as primary backend.
 
Architecture:
    - SpikingSSM: O(n) sequence processing with LIF neurons
    - MoE: sparse expert activation for large capacity / low inference cost
    - No attention mechanism — runs on any hardware
 
Usage:
    # Train
    python -m helena_ml.helena_llm.train --config nano
 
    # Inference (automatic via HybridLLM when model exists)
    from helena_ml.helena_llm import HelenaNetInference
    model = HelenaNetInference("./helena_memory/helena_net")
    response = model.chat([{"role": "user", "content": "Hello HELENA"}])
"""
from .config import HelenaNetConfig, HELENA_NANO, HELENA_BASE, HELENA_LARGE
from .tokenizer import HelenaTokenizer
from .architecture import HelenaNet
from .inference import HelenaNetInference
from .utils import RMSNorm, get_rms_norm
 
__all__ = [
    "HelenaNetConfig",
    "HELENA_NANO",
    "HELENA_BASE",
    "HELENA_LARGE",
    "HelenaTokenizer",
    "HelenaNet",
    "HelenaNetInference",
    "RMSNorm",
    "get_rms_norm",
]
