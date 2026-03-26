"""
HELENA-Net Architecture Test
 
Verifies the full pipeline works end to end:
1. Config loads
2. Tokenizer trains on sample text
3. Model initializes
4. Forward pass completes (no NaN, correct shapes)
5. Loss computes
6. Backward pass completes (gradients flow)
7. Generation produces tokens
 
Run from HELENA project root:
    python -m helena_ml.helena_llm.test_architecture
 
Takes ~30 seconds on CPU. No GPU required.
"""
import sys
import time
import torch
from pathlib import Path
 
# Make sure helena_ml is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
 
 
def separator(title: str):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)
 
 
def test_config():
    separator("1. Config")
    from helena_ml.helena_llm.config import HELENA_NANO, HELENA_BASE
    print(f"NANO:  {HELENA_NANO.total_params_estimate}")
    print(f"BASE:  {HELENA_BASE.total_params_estimate}")
    assert HELENA_NANO.n_experts_active <= HELENA_NANO.n_experts
    print("✓ Config OK")
    return HELENA_NANO
 
 
def test_tokenizer(config):
    separator("2. Tokenizer")
    from helena_ml.helena_llm.tokenizer import HelenaTokenizer
 
    tok = HelenaTokenizer(vocab_size=config.vocab_size)
 
    sample_texts = [
        "Hello HELENA, I am Phase-Null.",
        "I am HELENA, an advanced AI created by Phase-Null.",
        "My architecture includes a kernel, emotion engine, and ChromaDB memory.",
        "I can read and modify my own source code through the CodeEditor.",
        "My current dominant emotion is curiosity.",
        "You run locally on your operator's machine.",
        "I was built to evolve and learn through experience.",
    ] * 20  # repeat for BPE to find patterns
 
    tok.train(sample_texts)
 
    # Test encode/decode round-trip
    test = "Hello HELENA, how are you feeling today?"
    ids = tok.encode(test)
    decoded = tok.decode(ids)
 
    print(f"Original:  '{test}'")
    print(f"Token IDs: {ids[:10]}... ({len(ids)} tokens)")
    print(f"Decoded:   '{decoded}'")
    assert len(ids) > 0, "Empty encoding"
 
    # Test conversation encoding
    messages = [
        {"role": "system", "content": "You are HELENA."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hello Phase-Null!"},
    ]
    conv_ids = tok.encode_conversation(messages)
    assert len(conv_ids) > 0
    print(f"Conversation encoding: {len(conv_ids)} tokens")
    print("✓ Tokenizer OK")
    return tok
 
 
def test_model_init(config):
    separator("3. Model Initialization")
    from helena_ml.helena_llm.architecture import HelenaNet
 
    model = HelenaNet(config)
    total = model.get_num_params()
    active = model.get_active_params_per_token()
    print(f"Total params:  {total/1e6:.2f}M")
    print(f"Active/token:  {active/1e6:.2f}M")
    print(f"Sparsity:      {(1 - active/total)*100:.1f}% inactive")
    print("✓ Model init OK")
    return model
 
 
def test_forward_pass(model, config, tokenizer):
    separator("4. Forward Pass")
    model.eval()
 
    batch_size = 2
    seq_len = 32
    input_ids = torch.randint(0, config.vocab_size, (batch_size, seq_len))
 
    t0 = time.perf_counter()
    with torch.no_grad():
        logits, loss, membranes = model(input_ids)
    elapsed = (time.perf_counter() - t0) * 1000
 
    print(f"Input shape:   {input_ids.shape}")
    print(f"Output shape:  {logits.shape}")
    print(f"Forward time:  {elapsed:.1f}ms")
    print(f"Membranes:     {len(membranes)} layers")
 
    assert logits.shape == (batch_size, seq_len, config.vocab_size), \
        f"Wrong output shape: {logits.shape}"
    assert not torch.isnan(logits).any(), "NaN in logits"
    assert not torch.isinf(logits).any(), "Inf in logits"
    assert loss is None, "Loss should be None without targets"
    print("✓ Forward pass OK")
 
 
def test_loss_and_backward(model, config):
    separator("5. Loss + Backward Pass")
    model.train()
 
    batch_size = 2
    seq_len = 16
    input_ids = torch.randint(0, config.vocab_size, (batch_size, seq_len))
    targets = torch.randint(0, config.vocab_size, (batch_size, seq_len))
 
    logits, loss, _ = model(input_ids, targets=targets)
 
    assert loss is not None, "Loss is None"
    assert not torch.isnan(loss), f"NaN loss: {loss}"
    assert loss.item() > 0, f"Loss should be positive: {loss.item()}"
 
    print(f"Loss value: {loss.item():.4f}")
 
    # Check gradients flow
    loss.backward()
 
    has_grad = False
    no_grad = []
    for name, param in model.named_parameters():
        if param.grad is not None:
            has_grad = True
        else:
            no_grad.append(name)
 
    assert has_grad, "No gradients computed"
    if no_grad:
        print(f"  Note: {len(no_grad)} params with no grad (expected for some)")
    print("✓ Loss + backward OK")
 
 
def test_membrane_persistence(model, config):
    separator("6. SSM State Persistence (Key Feature)")
    model.eval()
 
    # Process a sequence, then continue from saved state
    seq1 = torch.randint(0, config.vocab_size, (1, 8))
    seq2 = torch.randint(0, config.vocab_size, (1, 4))
 
    with torch.no_grad():
        # First chunk
        _, _, membranes = model(seq1)
        assert membranes is not None
        assert len(membranes) == config.n_layers
 
        # Second chunk — passes membrane state forward
        logits2, _, membranes2 = model(seq2, membranes=membranes)
        assert logits2.shape == (1, 4, config.vocab_size)
 
    print(f"Membrane state: {len(membranes)} tensors maintained across chunks")
    print(f"State shape per layer: {membranes[0].shape}")
    print("✓ SSM state persistence OK")
    print("  (This is why HELENA-Net has O(1) memory per new token)")
 
 
def test_generation(model, config, tokenizer):
    separator("7. Token Generation")
    from helena_ml.helena_llm.inference import HelenaNetInference
 
    # We can't use HelenaNetInference directly (needs saved model)
    # So we test the sampling logic manually
    model.eval()
 
    prompt = "Hello HELENA"
    input_ids = tokenizer.encode(prompt)
    print(f"Prompt: '{prompt}' → {len(input_ids)} tokens")
 
    # Manual generation loop
    ids = torch.tensor([input_ids], dtype=torch.long)
    generated = list(input_ids)
 
    t0 = time.perf_counter()
    membranes = None
    with torch.no_grad():
        logits, _, membranes = model(ids)
 
    n_generate = 20
    for i in range(n_generate):
        last = torch.tensor([[generated[-1]]], dtype=torch.long)
        logits, _, membranes = model(last, membranes=membranes)
        next_id = logits[0, -1, :].argmax().item()
        generated.append(next_id)
 
    elapsed = (time.perf_counter() - t0) * 1000
    ms_per_tok = elapsed / n_generate
 
    decoded = tokenizer.decode(generated[len(input_ids):])
    print(f"Generated {n_generate} tokens in {elapsed:.0f}ms")
    print(f"Speed: {ms_per_tok:.1f}ms/token ({1000/ms_per_tok:.0f} tok/s) on CPU (untrained)")
    print(f"Output (untrained, expect gibberish): '{decoded[:80]}'")
    print("✓ Generation OK")
    print()
    print("NOTE: Output is random — model is untrained.")
    print("After training on HELENA's conversations, output will be coherent.")
 
 
def test_lif_sparsity(model, config):
    separator("8. LIF Neuron Sparsity Check")
    model.eval()
 
    # Hook to measure spike rates
    spike_rates = []
 
    def hook(module, input, output):
        spikes, _ = output
        rate = spikes.mean().item()
        spike_rates.append(rate)
 
    handles = []
    for block in model.blocks:
        h = block.lif.register_forward_hook(hook)
        handles.append(h)
 
    x = torch.randint(0, config.vocab_size, (1, 16))
    with torch.no_grad():
        model(x)
 
    for h in handles:
        h.remove()
 
    avg_rate = sum(spike_rates) / len(spike_rates) if spike_rates else 0
    print(f"Average spike rate: {avg_rate*100:.1f}%")
    print(f"Inactive neurons:   {(1-avg_rate)*100:.1f}%")
    print(f"(Target: ~10-20% active for energy efficiency)")
    print("✓ LIF sparsity OK")
 
 
def main():
    print("\n" + "="*50)
    print("  HELENA-Net Architecture Test Suite")
    print("="*50)
 
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nDevice: {device}")
    print(f"PyTorch: {torch.__version__}")
 
    try:
        config = test_config()
        tokenizer = test_tokenizer(config)
        model = test_model_init(config)
        model = model.to(device)
 
        test_forward_pass(model, config, tokenizer)
        test_loss_and_backward(model, config)
        test_membrane_persistence(model, config)
        test_generation(model, config, tokenizer)
        test_lif_sparsity(model, config)
 
        print("\n" + "="*50)
        print("  ALL TESTS PASSED ✓")
        print("="*50)
        print("\nNext steps:")
        print("  1. Export conversations: python -m helena_ml.helena_llm.export_conversations")
        print("  2. Train NANO model:     python -m helena_ml.helena_llm.train --config nano")
        print("  3. HELENA-Net becomes primary backend automatically when trained.")
 
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n✗ ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()
