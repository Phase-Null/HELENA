"""
HELENA-Net Utilities
 
Compatibility helpers and shared components.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
 
 
class RMSNorm(nn.Module):
    """
    Root Mean Square Layer Normalization.
 
    Faster than LayerNorm — no mean subtraction, just scale by RMS.
    Used throughout HELENA-Net.
 
    Implemented here for compatibility with PyTorch < 2.4 which lacks
    the built-in nn.RMSNorm.
    """
 
    def __init__(self, d: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d))
 
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [..., d]
        rms = x.pow(2).mean(dim=-1, keepdim=True).add(self.eps).sqrt()
        return x / rms * self.weight
 
 
def get_rms_norm(d: int) -> nn.Module:
    """Return RMSNorm — built-in if available, custom otherwise."""
    try:
        # PyTorch 2.4+
        return nn.RMSNorm(d)
    except AttributeError:
        return RMSNorm(d)
 
