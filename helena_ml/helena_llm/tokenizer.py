"""
HELENA-Net Tokenizer

Byte-Pair Encoding tokenizer trained on HELENA's conversation data.
Backed by the HuggingFace `tokenizers` library (Rust implementation) —
identical public API to the original pure-Python version, ~50-100x faster.

Vocabulary layout (always in this order, non-negotiable):
    IDs  0– 6  : 7 special tokens  (<pad> <bos> <eos> <unk> <user> <hele> <sys>)
    IDs  7–... : BPE-learned subword tokens
    Total      : 8192 (NANO config)

Why BPE:
    - Handles any Unicode input gracefully via ByteLevel pre-tokenizer
    - Compact vocabulary (8192 tokens covers HELENA's domain well)
    - Consistent with original tokenizer design intent
    - Rust backend makes training and encoding effectively instant
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional

from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.decoders import ByteLevel as ByteLevelDecoder


class HelenaTokenizer:
    """
    HELENA-Net BPE tokenizer — HuggingFace Rust backend.

    Special tokens (IDs are fixed and must never change — the model
    embedding matrix is built around this layout):
        <pad>  = 0   padding
        <bos>  = 1   beginning of sequence
        <eos>  = 2   end of sequence
        <unk>  = 3   unknown token
        <user> = 4   user turn marker
        <hele> = 5   HELENA turn marker
        <sys>  = 6   system prompt marker
    """

    # Fixed — must match architecture.py embedding table
    SPECIAL_TOKENS: Dict[str, int] = {
        "<pad>":  0,
        "<bos>":  1,
        "<eos>":  2,
        "<unk>":  3,
        "<user>": 4,
        "<hele>": 5,
        "<sys>":  6,
    }

    # In ID order — the trainer must see them in this exact sequence
    _SPECIAL_LIST = ["<pad>", "<bos>", "<eos>", "<unk>", "<user>", "<hele>", "<sys>"]

    def __init__(self, vocab_size: int = 8192):
        self.vocab_size = vocab_size
        self._tokenizer: Optional[Tokenizer] = None
        self._trained = False

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, texts: List[str]) -> None:
        """
        Train BPE on a list of text strings.

        Special tokens are added first (IDs 0-6), then BPE merges fill the
        remainder of the vocabulary up to vocab_size. Training is done in Rust
        via the HuggingFace tokenizers library — typically completes in seconds.
        """
        print(f"Training tokenizer on {len(texts)} texts...")

        tokenizer = Tokenizer(BPE(unk_token="<unk>"))
        tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)
        tokenizer.decoder       = ByteLevelDecoder()

        trainer = BpeTrainer(
            vocab_size=self.vocab_size,
            special_tokens=self._SPECIAL_LIST,   # first → guaranteed IDs 0-6
            min_frequency=2,
            show_progress=True,
        )

        tokenizer.train_from_iterator(texts, trainer=trainer)

        # Hard check: if special token IDs shifted, the model is broken
        for name, expected_id in self.SPECIAL_TOKENS.items():
            actual_id = tokenizer.token_to_id(name)
            if actual_id != expected_id:
                raise RuntimeError(
                    f"Special token ID mismatch: {name} expected {expected_id}, "
                    f"got {actual_id}. This would corrupt the model embedding table."
                )

        self._tokenizer = tokenizer
        self._trained   = True
        actual_vocab    = tokenizer.get_vocab_size()

        print(f"Tokenizer trained. Final vocab size: {actual_vocab}")

        if actual_vocab != self.vocab_size:
            print(
                f"  Note: vocab is {actual_vocab}, not {self.vocab_size}. "
                f"Training corpus may not have had enough unique pairs to fill "
                f"all merge slots. Consider updating config.vocab_size to match."
            )

    # ── Encode / Decode ───────────────────────────────────────────────────────

    def encode(self, text: str, add_special_tokens: bool = True) -> List[int]:
        """
        Encode text to a list of token IDs.

        add_special_tokens=True  → [<bos>] + tokens + [<eos>]
        add_special_tokens=False → tokens only (used internally by encode_conversation)
        """
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded.")

        ids = self._tokenizer.encode(text).ids

        if add_special_tokens:
            ids = [self.SPECIAL_TOKENS["<bos>"]] + ids + [self.SPECIAL_TOKENS["<eos>"]]

        return ids

    def decode(self, ids: List[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs back to a text string."""
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded.")

        if skip_special_tokens:
            special_ids = set(self.SPECIAL_TOKENS.values())
            ids = [i for i in ids if i not in special_ids]

        return self._tokenizer.decode(ids)

    # ── Conversation formatting ───────────────────────────────────────────────

    def encode_conversation(self, messages: List[Dict[str, str]]) -> List[int]:
        """
        Encode a full conversation into a flat token ID sequence.

        Format:
            <sys>  system_content
            <user> user_message
            <hele> assistant_response
            <eos>

        Role markers are injected as raw token IDs so the model learns
        turn boundaries from the token stream, not from text patterns.
        Multiple turns are concatenated — the model sees the full
        context window in one forward pass.
        """
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded.")

        ids: List[int] = []

        for msg in messages:
            role    = msg.get("role", "user")
            content = msg.get("content", "").strip()

            if not content:
                continue

            if role == "system":
                marker = self.SPECIAL_TOKENS["<sys>"]
            elif role == "user":
                marker = self.SPECIAL_TOKENS["<user>"]
            elif role in ("assistant", "helena", "hele"):
                marker = self.SPECIAL_TOKENS["<hele>"]
            else:
                continue  # unknown role — skip rather than corrupt the sequence

            content_ids = self.encode(content, add_special_tokens=False)
            ids += [marker] + content_ids

        ids.append(self.SPECIAL_TOKENS["<eos>"])
        return ids

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """
        Save tokenizer to disk.

        Writes two files:
            tokenizer.json     — HuggingFace native format (the full tokenizer)
            helena_meta.json   — vocab_size and actual vocab size for the wrapper
        """
        if self._tokenizer is None:
            raise RuntimeError("Nothing to save — tokenizer has not been trained.")

        Path(path).mkdir(parents=True, exist_ok=True)

        self._tokenizer.save(os.path.join(path, "tokenizer.json"))

        with open(os.path.join(path, "helena_meta.json"), "w") as f:
            json.dump({
                "vocab_size":        self.vocab_size,
                "actual_vocab_size": self._tokenizer.get_vocab_size(),
                "trained":           self._trained,
            }, f, indent=2)

        print(f"Tokenizer saved to {path}")

    @classmethod
    def load(cls, path: str) -> "HelenaTokenizer":
        """Load tokenizer from disk. Expects tokenizer.json in the given directory."""
        tok_path  = os.path.join(path, "tokenizer.json")
        meta_path = os.path.join(path, "helena_meta.json")

        if not os.path.exists(tok_path):
            raise FileNotFoundError(f"No tokenizer.json found in {path}")

        vocab_size = 8192
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            vocab_size = meta.get("vocab_size", 8192)

        instance = cls(vocab_size=vocab_size)
        instance._tokenizer = Tokenizer.from_file(tok_path)
        instance._trained   = True
        return instance

    # ── Utilities ─────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        if self._tokenizer is None:
            return len(self.SPECIAL_TOKENS)
        return self._tokenizer.get_vocab_size()

    def get_token_id(self, token: str) -> Optional[int]:
        """Token string → ID. Checks special tokens first."""
        if token in self.SPECIAL_TOKENS:
            return self.SPECIAL_TOKENS[token]
        if self._tokenizer is None:
            return None
        return self._tokenizer.token_to_id(token)

    def get_id_token(self, id: int) -> Optional[str]:
        """ID → token string."""
        reverse = {v: k for k, v in self.SPECIAL_TOKENS.items()}
        if id in reverse:
            return reverse[id]
        if self._tokenizer is None:
            return None
        return self._tokenizer.id_to_token(id)
