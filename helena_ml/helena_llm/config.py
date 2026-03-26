"""
HELENA-Net Configuration
 
SpikingSSM-MoE: Spiking State Space Model with Mixture of Experts.
 
A novel architecture designed for fast local inference:
- No attention mechanism — O(n) not O(n²)
- Leaky Integrate-and-Fire neurons — sparse, brain-inspired activation
- State Space Model core — infinite context in fixed memory
- Mixture of Experts — large capacity, small inference cost
"""
from dataclasses import dataclass, field
from typing import Optional
 
 
@dataclass
class HelenaNetConfig:
    """
    Configuration for HELENA-Net.
 
    Design targets:
    - <500ms response on CPU (no GPU required)
    - ~50M active parameters per forward pass (MoE keeps this low)
    - Runs on 4GB RAM minimum
    - Trained on HELENA's own conversation history
    """
 
    # Vocabulary
    vocab_size: int = 8192          # Small vocab = fast embedding lookup
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2
    unk_token_id: int = 3
 
    # Model dimensions
    d_model: int = 512              # Core hidden dimension
    d_state: int = 64               # SSM state dimension (the "memory")
    d_conv: int = 4                 # Local convolution width in SSM
    d_inner: int = 1024             # Expanded inner dimension (SSM)
    n_layers: int = 12              # Number of SpikingSSM-MoE blocks
 
    # Spiking neuron parameters (Leaky Integrate-and-Fire)
    lif_threshold: float = 0.5     # Membrane potential threshold to fire
    lif_leak: float = 0.9          # Membrane decay factor per step (beta)
    lif_reset: float = 0.0         # Reset potential after firing
    surrogate_slope: float = 25.0  # Slope for surrogate gradient (training)
 
    # Mixture of Experts
    n_experts: int = 8              # Total expert networks
    n_experts_active: int = 2       # Experts activated per token
    expert_capacity_factor: float = 1.25  # Load balancing headroom
    d_expert: int = 2048            # Expert FFN hidden dimension
 
    # Training
    max_seq_len: int = 2048
    dropout: float = 0.1
    learning_rate: float = 3e-4
    weight_decay: float = 0.01
    warmup_steps: int = 500
    max_steps: int = 10000
    batch_size: int = 8
    grad_clip: float = 1.0
 
    # Inference
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    max_new_tokens: int = 512
    repetition_penalty: float = 1.1
 
    # Paths
    save_path: str = "./helena_memory/helena_net"
    conversation_data_path: str = "./helena_memory/conversations.jsonl"
 
    @property
    def total_params_estimate(self) -> str:
        """Rough parameter count estimate."""
        embed = self.vocab_size * self.d_model
        ssm_per_layer = (
            self.d_model * self.d_inner * 2 +   # input/output projections
            self.d_inner * self.d_state * 2 +    # B, C matrices
            self.d_state +                        # A diagonal
            self.d_inner * self.d_conv            # local conv
        )
        moe_per_layer = (
            self.n_experts * (                   # all experts
                self.d_model * self.d_expert +
                self.d_expert * self.d_model
            ) +
            self.d_model * self.n_experts        # router
        )
        total = embed + self.n_layers * (ssm_per_layer + moe_per_layer)
        active = embed + self.n_layers * (ssm_per_layer + self.n_experts_active * (
            self.d_model * self.d_expert + self.d_expert * self.d_model
        ))
        return (f"Total: ~{total/1e6:.0f}M params | "
                f"Active per token: ~{active/1e6:.0f}M params")
 
 
# Default config — small and fast
HELENA_NANO = HelenaNetConfig(
    d_model=256, d_state=32, d_inner=512, n_layers=6,
    n_experts=4, n_experts_active=1, d_expert=1024,
    vocab_size=8192, max_seq_len=1024,
)
 
# Standard config — balanced
HELENA_BASE = HelenaNetConfig()
 
# Large config — maximum capability
HELENA_LARGE = HelenaNetConfig(
    d_model=1024, d_state=128, d_inner=2048, n_layers=24,
    n_experts=16, n_experts_active=2, d_expert=4096,
    vocab_size=16384, max_seq_len=4096,
)
 
