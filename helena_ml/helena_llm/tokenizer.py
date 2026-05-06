"""
HELENA-Net Tokenizer — v2

Byte-Pair Encoding tokenizer backed by the HuggingFace `tokenizers` library
(Rust implementation). Identical public API to the original pure-Python version,
~50-100x faster to train and encode.

Key design decisions:
    - ByteLevel pre-tokenizer: every byte maps to a unique visible character
      before BPE. Guarantees zero OOV tokens on any Unicode input.
    - Trained primarily on HELENA conversation data so merges reflect HELENA's
      actual domain vocabulary (AEGIS, kernel, emotion engine, etc.) rather
      than generic English. This directly improves training efficiency because
      HELENA-specific phrases consume fewer tokens, fitting more content into
      each 256-token context window.
    - General conversation data (OASST2) is included at a small ratio to
      ensure broad language coverage without diluting domain specificity.

Vocabulary layout (fixed, non-negotiable — model embedding table depends on this):
    IDs  0– 6  : 7 special tokens
    IDs  7–... : BPE-learned subword merges (domain-weighted)
    Total      : 8192

Special token IDs:
    <pad>  = 0    padding / unused positions
    <bos>  = 1    beginning of sequence
    <eos>  = 2    end of sequence
    <unk>  = 3    unknown (should be rare with ByteLevel)
    <user> = 4    user turn marker
    <hele> = 5    HELENA turn marker
    <sys>  = 6    system prompt marker
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
    HELENA-Net BPE tokenizer — HuggingFace Rust backend, domain-weighted vocabulary.

    The tokenizer is trained to merge HELENA-specific vocabulary aggressively.
    This means phrases like "emotion engine", "AEGIS", "kernel", "operator"
    encode into fewer tokens — more content fits in each context window, and
    training converges faster because the model sees more complete thoughts
    per batch.
    """

    # Fixed — must match architecture.py embedding table layout exactly.
    SPECIAL_TOKENS: Dict[str, int] = {
        "<pad>":  0,
        "<bos>":  1,
        "<eos>":  2,
        "<unk>":  3,
        "<user>": 4,
        "<hele>": 5,
        "<sys>":  6,
    }

    # Ordered list — BpeTrainer assigns IDs in this exact order.
    _SPECIAL_LIST = ["<pad>", "<bos>", "<eos>", "<unk>", "<user>", "<hele>", "<sys>"]

    def __init__(self, vocab_size: int = 8192):
        self.vocab_size  = vocab_size
        self._tokenizer: Optional[Tokenizer] = None
        self._trained    = False

    # ── Training ──────────────────────────────────────────────────────────────

    def train(self, texts: List[str]) -> None:
        """
        Train BPE on a list of text strings.

        The caller is responsible for passing texts in the right order and ratio.
        Recommended: HELENA conversations first (dominant), OASST2 second (small),
        domain vocabulary strings third (tiny). See the notebook for the exact
        preparation logic.

        Training runs in Rust — typically 5-15 seconds on 20k+ texts.
        """
        print(f"Training tokenizer on {len(texts)} texts...")

        tokenizer             = Tokenizer(BPE(unk_token="<unk>"))
        tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)
        tokenizer.decoder       = ByteLevelDecoder()

        trainer = BpeTrainer(
            vocab_size=self.vocab_size,
            special_tokens=self._SPECIAL_LIST,  # IDs 0-6, in order, guaranteed
            min_frequency=2,                    # ignore pairs seen only once
            show_progress=True,
        )

        tokenizer.train_from_iterator(texts, trainer=trainer)

        # Hard verification — if IDs shifted, the model embedding table is wrong.
        for name, expected_id in self.SPECIAL_TOKENS.items():
            actual_id = tokenizer.token_to_id(name)
            if actual_id != expected_id:
                raise RuntimeError(
                    f"Special token ID mismatch for {name}: "
                    f"expected {expected_id}, got {actual_id}. "
                    f"This would silently corrupt the model. Aborting."
                )

        self._tokenizer = tokenizer
        self._trained   = True
        actual_vocab    = tokenizer.get_vocab_size()

        print(f"Tokenizer trained. Vocab size: {actual_vocab}")

        if actual_vocab != self.vocab_size:
            print(
                f"  WARNING: expected {self.vocab_size}, got {actual_vocab}. "
                f"Training corpus may not have enough unique pairs to fill all "
                f"merge slots. Update NANO config vocab_size to {actual_vocab} "
                f"before training the model, or add more text and retrain."
            )

    # ── Encode ────────────────────────────────────────────────────────────────

    def encode(self, text: str, add_special_tokens: bool = True) -> List[int]:
        """
        Encode a text string to token IDs.

        add_special_tokens=True  →  [<bos>] + content_ids + [<eos>]
        add_special_tokens=False →  content_ids only
                                    (used by encode_conversation for role markers)
        """
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded. Call train() or load() first.")

        ids = self._tokenizer.encode(text).ids

        if add_special_tokens:
            ids = [self.SPECIAL_TOKENS["<bos>"]] + ids + [self.SPECIAL_TOKENS["<eos>"]]

        return ids

    # ── Decode ────────────────────────────────────────────────────────────────

    def decode(self, ids: List[int], skip_special_tokens: bool = True) -> str:
        """Decode a list of token IDs back to a text string."""
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded.")

        if skip_special_tokens:
            special_ids = set(self.SPECIAL_TOKENS.values())
            ids = [i for i in ids if i not in special_ids]

        return self._tokenizer.decode(ids)

    # ── Conversation encoding ─────────────────────────────────────────────────

    def encode_conversation(self, messages: List[Dict[str, str]]) -> List[int]:
        """
        Encode a full conversation as a flat token ID sequence.

        HELENA's conversation format:
            <sys>  [system message content]
            <user> [user message content]
            <hele> [HELENA response content]
            <eos>

        Role markers are injected as raw token IDs — not encoded as text.
        This is critical: the model must learn that <user>=4 and <hele>=5 signal
        turn boundaries, not from seeing the literal string "<user>" in text.

        Multiple turns are concatenated into one sequence. The model learns from
        the full conversation context, not just isolated pairs.
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
                # Unknown role — skip silently. Never corrupt the sequence.
                continue

            content_ids = self.encode(content, add_special_tokens=False)
            ids += [marker] + content_ids

        # Every conversation ends with <eos>
        ids.append(self.SPECIAL_TOKENS["<eos>"])
        return ids

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """
        Save tokenizer to disk.

        Creates two files in the given directory:
            tokenizer.json      HuggingFace native format — the full BPE model
            helena_meta.json    Wrapper metadata (vocab_size, actual size)

        The directory is created if it doesn't exist.
        The tokenizer.json format is compatible with HuggingFace AutoTokenizer
        for inspection, but should always be loaded through this class.
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
                "version":           2,
            }, f, indent=2)

        print(f"Tokenizer saved to {path}")

    @classmethod
    def load(cls, path: str) -> "HelenaTokenizer":
        """
        Load a saved tokenizer from disk.

        Expects tokenizer.json in the given directory.
        Falls back to vocab_size=8192 if helena_meta.json is missing.
        """
        tok_path  = os.path.join(path, "tokenizer.json")
        meta_path = os.path.join(path, "helena_meta.json")

        if not os.path.exists(tok_path):
            raise FileNotFoundError(
                f"No tokenizer.json found in {path}. "
                f"Train the tokenizer first (Cell 5 in the notebook)."
            )

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
        """Returns the actual vocabulary size."""
        if self._tokenizer is None:
            return len(self.SPECIAL_TOKENS)
        return self._tokenizer.get_vocab_size()

    def get_token_id(self, token: str) -> Optional[int]:
        """Token string → ID. Checks special tokens dict first."""
        if token in self.SPECIAL_TOKENS:
            return self.SPECIAL_TOKENS[token]
        if self._tokenizer is None:
            return None
        return self._tokenizer.token_to_id(token)

    def get_id_token(self, token_id: int) -> Optional[str]:
        """ID → token string."""
        reverse = {v: k for k, v in self.SPECIAL_TOKENS.items()}
        if token_id in reverse:
            return reverse[token_id]
        if self._tokenizer is None:
            return None
        return self._tokenizer.id_to_token(token_id)

    def token_efficiency(self, text: str) -> float:
        """
        Returns tokens-per-character ratio for a given text.
        Lower is better — fewer tokens means more content per context window.
        Useful for comparing tokenizer versions on HELENA-specific text.
        """
        if self._tokenizer is None:
            raise RuntimeError("Tokenizer not trained or loaded.")
        ids = self._tokenizer.encode(text).ids
        return len(ids) / max(len(text), 1)
