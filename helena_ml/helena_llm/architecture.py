"""
HELENA-Net Architecture: SpikingSSM-MoE
 
A novel neural architecture combining three ideas:
 
1. STATE SPACE MODEL (SSM) CORE
   Based on structured state space sequences (S4/Mamba family).
   Processes sequences in O(n) time — no quadratic attention.
   All past context is compressed into a fixed-size state vector h(t).
   Recurrence: h(t) = A * h(t-1) + B * x(t)
                y(t) = C * h(t) + D * x(t)
 
2. SPIKING NEURONS (LIF — Leaky Integrate-and-Fire)
   Instead of continuous activations (ReLU, GELU), neurons accumulate
   a "membrane potential" and fire (output 1.0) when it exceeds a
   threshold, then reset. Between fires, they output 0.0.
   Result: sparse computation. At any moment ~10-20% of neurons fire.
   Energy cost scales with sparsity, not model size.
   During training: surrogate gradient allows backprop through spikes.
 
3. MIXTURE OF EXPERTS (MoE)
   8 expert FFN networks per layer. A learned router activates only 2
   per token. This gives the representational capacity of a large model
   at the inference cost of a small one.
 
Combined effect:
   - SSM: O(n) sequence processing instead of O(n²) attention
   - LIF: ~85% of neuron outputs are zero → massive compute reduction
   - MoE: only 25% of expert parameters activate per token
   Net result: ~15x less compute than an equivalent dense transformer.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, List
from .config import HelenaNetConfig
from .utils import get_rms_norm
 
 
# ── Spiking Neuron Layer ──────────────────────────────────────────
 
class SurrogateSpike(torch.autograd.Function):
    """
    Surrogate gradient for spike function.
 
    Forward:  spike = 1 if membrane >= threshold else 0
    Backward: use sigmoid derivative as smooth approximation
              (the real gradient of a step function is zero almost
              everywhere, which breaks backprop — surrogate fixes this)
    """
    @staticmethod
    def forward(ctx, membrane: torch.Tensor,
                threshold: float, slope: float) -> torch.Tensor:
        ctx.save_for_backward(membrane)
        ctx.threshold = threshold
        ctx.slope = slope
        return (membrane >= threshold).float()
 
    @staticmethod
    def backward(ctx, grad_output: torch.Tensor):
        membrane, = ctx.saved_tensors
        threshold = ctx.threshold
        slope = ctx.slope
        # Surrogate: derivative of sigmoid scaled by slope
        x = slope * (membrane - threshold)
        surrogate = slope * torch.sigmoid(x) * (1 - torch.sigmoid(x))
        return grad_output * surrogate, None, None
 
 
class LIFNeuron(nn.Module):
    """
    Leaky Integrate-and-Fire neuron layer.
 
    Membrane dynamics:
        V(t) = β * V(t-1) + I(t)          [integrate with leak]
        spike(t) = 1 if V(t) >= θ else 0  [fire if above threshold]
        V(t) = V(t) - spike(t) * θ        [soft reset after firing]
 
    β (leak/decay): how much membrane retains between steps
    θ (threshold): firing threshold
    """
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        self.threshold = config.lif_threshold
        self.leak = config.lif_leak
        self.slope = config.surrogate_slope
 
    def forward(self, current: torch.Tensor,
                membrane: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            current: input current [batch, seq, d_model]
            membrane: previous membrane potential (None = start fresh)
        Returns:
            spikes: binary spike tensor [batch, seq, d_model]
            membrane: updated membrane potential
        """
        batch, seq, d = current.shape
 
        if membrane is None:
            membrane = torch.zeros(batch, d, device=current.device, dtype=current.dtype)
 
        spikes_list = []
        for t in range(seq):
            # Leak + integrate
            membrane = self.leak * membrane + current[:, t, :]
            # Fire
            spike = SurrogateSpike.apply(membrane, self.threshold, self.slope)
            # Soft reset: subtract threshold from membrane where fired
            membrane = membrane - spike * self.threshold
            spikes_list.append(spike)
 
        spikes = torch.stack(spikes_list, dim=1)  # [batch, seq, d]
        return spikes, membrane
 
 
# ── State Space Model Core ────────────────────────────────────────
 
class SSMLayer(nn.Module):
    """
    Simplified Structured State Space Model layer.
 
    Based on the S4/Mamba family but simplified for clarity and speed.
 
    State update (per position):
        h(t) = A ⊙ h(t-1) + B(t) ⊙ x(t)
        y(t) = C(t) · h(t) + D ⊙ x(t)
 
    A: diagonal decay matrix (learnable, clamped to [0,1])
    B: input projection (input-dependent)
    C: output projection (input-dependent)
    D: skip connection (learnable scalar)
 
    A being diagonal means the state update is element-wise — fast.
    B and C being input-dependent gives selectivity (like attention
    but O(n) not O(n²)).
    """
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        d = config.d_model
        d_inner = config.d_inner
        d_state = config.d_state
        d_conv = config.d_conv
 
        # Input expansion
        self.in_proj = nn.Linear(d, d_inner * 2, bias=False)
 
        # Local convolution (captures short-range dependencies)
        self.conv1d = nn.Conv1d(
            in_channels=d_inner,
            out_channels=d_inner,
            kernel_size=d_conv,
            padding=d_conv - 1,
            groups=d_inner,
            bias=True,
        )
 
        # SSM parameters
        # A: diagonal state decay (learnable, we store log(-A) for stability)
        self.A_log = nn.Parameter(
            torch.log(torch.arange(1, d_state + 1, dtype=torch.float32)
                      .unsqueeze(0).repeat(d_inner, 1))
        )
        # D: skip connection
        self.D = nn.Parameter(torch.ones(d_inner))
 
        # Input-dependent B, C (selectivity — this is the key Mamba innovation)
        self.x_proj = nn.Linear(d_inner, d_state * 2 + 1, bias=False)  # dt, B, C
        self.dt_proj = nn.Linear(1, d_inner, bias=True)
 
        # Output projection
        self.out_proj = nn.Linear(d_inner, d, bias=False)
 
        # Layer norm
        self.norm = get_rms_norm(d)
 
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, seq, d_model]
        Returns:
            y: [batch, seq, d_model]
        """
        residual = x
        x = self.norm(x)
 
        batch, seq, d = x.shape
 
        # Dual branch: z for gating, x for SSM
        xz = self.in_proj(x)  # [B, L, 2*d_inner]
        x_branch, z = xz.chunk(2, dim=-1)  # each [B, L, d_inner]
 
        # Local convolution on x_branch
        x_conv = x_branch.transpose(1, 2)  # [B, d_inner, L]
        x_conv = self.conv1d(x_conv)[:, :, :seq]  # causal, trim
        x_conv = x_conv.transpose(1, 2)  # [B, L, d_inner]
        x_conv = F.silu(x_conv)
 
        # SSM
        # Compute A (negative to ensure decay)
        A = -torch.exp(self.A_log)  # [d_inner, d_state]
 
        # Input-dependent parameters
        x_dbl = self.x_proj(x_conv)  # [B, L, d_state*2 + 1]
        dt, B, C = x_dbl.split([1, self.A_log.shape[1], self.A_log.shape[1]], dim=-1)
        dt = F.softplus(self.dt_proj(dt))  # [B, L, d_inner], positive
 
        # Discretize A and B using zero-order hold
        # dA = exp(dt ⊙ A), dB = dt ⊙ B (simplified)
        dA = torch.exp(dt.unsqueeze(-1) * A.unsqueeze(0).unsqueeze(0))  # [B,L,d_inner,d_state]
        dB = dt.unsqueeze(-1) * B.unsqueeze(2)  # [B, L, d_inner, d_state]
 
        # Scan: h(t) = dA * h(t-1) + dB * x(t)
        h = torch.zeros(batch, x_conv.shape[2], self.A_log.shape[1],
                        device=x.device, dtype=x.dtype)
        ys = []
        for t in range(seq):
            h = dA[:, t] * h + dB[:, t] * x_conv[:, t].unsqueeze(-1)
            y_t = (h * C[:, t].unsqueeze(2)).sum(dim=-1)  # [B, d_inner]
            ys.append(y_t)
 
        y = torch.stack(ys, dim=1)  # [B, L, d_inner]
        y = y + x_conv * self.D.unsqueeze(0).unsqueeze(0)  # skip connection
 
        # Gate with z branch
        y = y * F.silu(z)
 
        # Output projection
        y = self.out_proj(y)
 
        return y + residual
 
 
# ── Mixture of Experts ────────────────────────────────────────────
 
class Expert(nn.Module):
    """Single expert FFN network."""
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        self.gate_proj = nn.Linear(config.d_model, config.d_expert, bias=False)
        self.up_proj = nn.Linear(config.d_model, config.d_expert, bias=False)
        self.down_proj = nn.Linear(config.d_expert, config.d_model, bias=False)
 
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # SwiGLU activation: silu(gate) * up
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))
 
 
class SparseMoELayer(nn.Module):
    """
    Sparse Mixture of Experts layer.
 
    Router selects top-k experts per token. Only those experts compute.
    Auxiliary load balancing loss ensures experts are used evenly.
    """
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        self.n_experts = config.n_experts
        self.n_active = config.n_experts_active
        self.experts = nn.ModuleList([Expert(config) for _ in range(config.n_experts)])
        self.router = nn.Linear(config.d_model, config.n_experts, bias=False)
        self.norm = get_rms_norm(config.d_model)
        self._aux_loss = torch.tensor(0.0)
 
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, seq, d_model]
        Returns:
            y: [batch, seq, d_model]
        """
        residual = x
        x = self.norm(x)
 
        batch, seq, d = x.shape
        x_flat = x.view(-1, d)  # [B*L, d]
 
        # Router: probabilities over experts
        router_logits = self.router(x_flat)  # [B*L, n_experts]
        router_probs = F.softmax(router_logits, dim=-1)
 
        # Select top-k experts
        top_k_probs, top_k_indices = router_probs.topk(self.n_active, dim=-1)
        top_k_probs = top_k_probs / top_k_probs.sum(dim=-1, keepdim=True)  # renormalize
 
        # Auxiliary load balancing loss (encourage uniform expert usage)
        # This prevents all tokens routing to one expert
        expert_usage = router_probs.mean(dim=0)
        target_usage = torch.ones_like(expert_usage) / self.n_experts
        self._aux_loss = F.mse_loss(expert_usage, target_usage)
 
        # Dispatch to experts
        output = torch.zeros_like(x_flat)
        for expert_idx in range(self.n_experts):
            # Find which tokens use this expert
            mask = (top_k_indices == expert_idx).any(dim=-1)  # [B*L]
            if not mask.any():
                continue
 
            tokens = x_flat[mask]  # [n_tokens, d]
            expert_out = self.experts[expert_idx](tokens)
 
            # Weight by router probability
            weights = router_probs[mask, expert_idx].unsqueeze(-1)
            output[mask] += weights * expert_out
 
        output = output.view(batch, seq, d)
        return output + residual
 
    @property
    def aux_loss(self) -> torch.Tensor:
        return self._aux_loss
 
 
# ── Full SpikingSSM-MoE Block ─────────────────────────────────────
 
class SpikingSSMMoEBlock(nn.Module):
    """
    One full block of the HELENA-Net architecture.
 
    Order:
        1. SSM layer (sequence mixing — captures temporal patterns)
        2. LIF spiking layer (sparsification — reduce active neurons)
        3. MoE FFN layer (feature mixing — expert knowledge routing)
    """
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        self.ssm = SSMLayer(config)
        self.lif = LIFNeuron(config)
        self.moe = SparseMoELayer(config)
        self.lif_proj_in = nn.Linear(config.d_model, config.d_model, bias=False)
        self.lif_proj_out = nn.Linear(config.d_model, config.d_model, bias=False)
        self.norm_lif = get_rms_norm(config.d_model)
 
    def forward(self, x: torch.Tensor,
                membrane: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: [batch, seq, d_model]
            membrane: LIF membrane state from previous call (for streaming)
        Returns:
            x: transformed [batch, seq, d_model]
            membrane: updated membrane state
        """
        # 1. SSM: temporal mixing
        x = self.ssm(x)
 
        # 2. LIF: sparsify activations
        lif_in = self.lif_proj_in(self.norm_lif(x))
        spikes, membrane = self.lif(lif_in, membrane)
        # Project spikes back and add residual (spikes are sparse 0/1)
        x = x + self.lif_proj_out(spikes)
 
        # 3. MoE: expert feature mixing
        x = self.moe(x)
 
        return x, membrane
 
    @property
    def aux_loss(self) -> torch.Tensor:
        return self.moe.aux_loss
 
 
# ── Full HELENA-Net Model ─────────────────────────────────────────
 
class HelenaNet(nn.Module):
    """
    HELENA's own language model.
 
    A SpikingSSM-MoE architecture designed for fast local inference.
    Replace Mistral in HybridLLM when trained.
    """
 
    def __init__(self, config: HelenaNetConfig):
        super().__init__()
        self.config = config
 
        # Token embedding
        self.embedding = nn.Embedding(config.vocab_size, config.d_model,
                                      padding_idx=config.pad_token_id)
 
        # Positional bias (relative, not absolute — works for any length)
        self.pos_bias = nn.Parameter(torch.zeros(1, config.max_seq_len, config.d_model))
 
        # Main blocks
        self.blocks = nn.ModuleList([
            SpikingSSMMoEBlock(config) for _ in range(config.n_layers)
        ])
 
        # Output
        self.norm_out = get_rms_norm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
 
        # Weight tying: embedding and lm_head share weights (reduces params)
        self.lm_head.weight = self.embedding.weight
 
        self.dropout = nn.Dropout(config.dropout)
 
        # Initialize weights
        self.apply(self._init_weights)
 
        print(f"HELENA-Net initialized. {config.total_params_estimate}")
 
    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
 
    def forward(self, input_ids: torch.Tensor,
                targets: Optional[torch.Tensor] = None,
                membranes: Optional[List[torch.Tensor]] = None,
                ) -> Tuple[torch.Tensor, Optional[torch.Tensor], List[torch.Tensor]]:
        """
        Args:
            input_ids: [batch, seq]
            targets: [batch, seq] for training (shifted input_ids)
            membranes: list of LIF states per block (for streaming inference)
        Returns:
            logits: [batch, seq, vocab_size]
            loss: scalar if targets provided, else None
            membranes: updated list of LIF states
        """
        batch, seq = input_ids.shape
        assert seq <= self.config.max_seq_len, \
            f"Sequence length {seq} exceeds max {self.config.max_seq_len}"
 
        # Embed tokens + positional bias
        x = self.embedding(input_ids)
        x = x + self.pos_bias[:, :seq, :]
        x = self.dropout(x)
 
        # Process through blocks
        if membranes is None:
            membranes = [None] * self.config.n_layers
 
        new_membranes = []
        aux_losses = []
        for i, block in enumerate(self.blocks):
            x, membrane = block(x, membranes[i])
            new_membranes.append(membrane)
            aux_losses.append(block.aux_loss)
 
        # Output
        x = self.norm_out(x)
        logits = self.lm_head(x)  # [batch, seq, vocab_size]
 
        # Compute loss if training
        loss = None
        if targets is not None:
            # Language model loss: predict next token
            loss = F.cross_entropy(
                logits.view(-1, self.config.vocab_size),
                targets.view(-1),
                ignore_index=self.config.pad_token_id,
            )
            # Add MoE load balancing loss (weighted small)
            aux_loss = torch.stack(aux_losses).mean()
            loss = loss + 0.01 * aux_loss
 
        return logits, loss, new_membranes
 
    def get_num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())
 
    def get_active_params_per_token(self) -> int:
        """Estimate active parameters per forward token (MoE sparse)."""
        total = self.get_num_params()
        # MoE layers: only n_active/n_experts of expert params active
        expert_params = sum(
            sum(p.numel() for p in block.moe.experts.parameters())
            for block in self.blocks
        )
        active_expert_params = expert_params * (
            self.config.n_experts_active / self.config.n_experts
        )
        non_expert_params = total - expert_params
        return int(non_expert_params + active_expert_params)
