"""
HELENA-Net Tokenizer
 
Lightweight Byte-Pair Encoding tokenizer trained on HELENA's conversation
data. No external dependencies — pure Python.
 
Why BPE:
- Handles any input (falls back to byte-level)
- Compact vocabulary (8192 tokens covers HELENA's domain well)
- Fast encode/decode in pure Python
- Can be trained on HELENA's own conversation history
"""
import re
import json
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
 
 
class HelenaTokenizer:
    """
    Byte-Pair Encoding tokenizer.
 
    Special tokens:
        <pad>  = 0
        <bos>  = 1   (beginning of sequence)
        <eos>  = 2   (end of sequence)
        <unk>  = 3   (unknown)
        <user> = 4   (user turn marker)
        <hele> = 5   (HELENA turn marker)
        <sys>  = 6   (system prompt marker)
    """
 
    SPECIAL_TOKENS = {
        "<pad>": 0,
        "<bos>": 1,
        "<eos>": 2,
        "<unk>": 3,
        "<user>": 4,
        "<hele>": 5,
        "<sys>": 6,
    }
 
    def __init__(self, vocab_size: int = 8192):
        self.vocab_size = vocab_size
        self.token_to_id: Dict[str, int] = dict(self.SPECIAL_TOKENS)
        self.id_to_token: Dict[int, str] = {v: k for k, v in self.token_to_id.items()}
        self.merges: List[Tuple[str, str]] = []
        self._trained = False
 
    # ── Training ──────────────────────────────────────────────────
 
    def train(self, texts: List[str]) -> None:
        """Train BPE on a list of text strings."""
        print(f"Training tokenizer on {len(texts)} texts...")
 
        # Step 1: Build initial character vocabulary from byte values
        vocab = self._get_initial_vocab(texts)
 
        # Step 2: BPE merges
        num_merges = self.vocab_size - len(self.SPECIAL_TOKENS) - 256  # 256 byte tokens
        next_id = len(self.SPECIAL_TOKENS) + 256  # after special + byte tokens
 
        # Add byte tokens first
        for i in range(256):
            byte_tok = f"<byte_{i}>"
            self.token_to_id[byte_tok] = len(self.SPECIAL_TOKENS) + i
            self.id_to_token[len(self.SPECIAL_TOKENS) + i] = byte_tok
 
        for merge_idx in range(num_merges):
            # Find most frequent pair
            pairs = self._get_pair_freqs(vocab)
            if not pairs:
                break
 
            best_pair = max(pairs, key=pairs.get)
            new_token = best_pair[0] + best_pair[1]
 
            # Add to vocabulary
            self.token_to_id[new_token] = next_id
            self.id_to_token[next_id] = new_token
            self.merges.append(best_pair)
            next_id += 1
 
            # Update vocab
            vocab = self._merge_pair(vocab, best_pair, new_token)
 
            if merge_idx % 500 == 0:
                print(f"  Merge {merge_idx}/{num_merges} — vocab size: {next_id}")
 
        self._trained = True
        print(f"Tokenizer trained. Final vocab size: {len(self.token_to_id)}")
 
    def _get_initial_vocab(self, texts: List[str]) -> Dict[Tuple[str, ...], int]:
        """Build initial word-frequency vocab using byte-level tokenization."""
        word_freqs: Dict[str, int] = defaultdict(int)
        for text in texts:
            for word in text.split():
                word_freqs[word] += 1
 
        # Represent each word as tuple of byte tokens
        vocab: Dict[Tuple[str, ...], int] = {}
        for word, freq in word_freqs.items():
            # Encode word as bytes, wrap each byte as a token
            byte_toks = tuple(f"<byte_{b}>" for b in word.encode("utf-8"))
            # Add word boundary marker to last token
            byte_toks = byte_toks[:-1] + (byte_toks[-1] + "</w>",)
            vocab[byte_toks] = freq
 
        return vocab
 
    def _get_pair_freqs(self, vocab: Dict[Tuple[str, ...], int]) -> Dict[Tuple[str, str], int]:
        """Count frequency of all adjacent pairs."""
        pairs: Dict[Tuple[str, str], int] = defaultdict(int)
        for word, freq in vocab.items():
            for i in range(len(word) - 1):
                pairs[(word[i], word[i + 1])] += freq
        return pairs
 
    def _merge_pair(self, vocab: Dict, pair: Tuple[str, str],
                    new_token: str) -> Dict:
        """Merge all occurrences of pair into new_token."""
        new_vocab = {}
        for word, freq in vocab.items():
            new_word = []
            i = 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == pair[0] and word[i+1] == pair[1]:
                    new_word.append(new_token)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            new_vocab[tuple(new_word)] = freq
        return new_vocab
 
    # ── Encode / Decode ───────────────────────────────────────────
 
    def encode(self, text: str, add_special_tokens: bool = True) -> List[int]:
        """Encode text to token IDs."""
        if not self._trained and len(self.token_to_id) <= len(self.SPECIAL_TOKENS) + 256:
            # Fallback: byte-level encoding
            return self._byte_encode(text, add_special_tokens)
 
        tokens = self._tokenize(text)
        ids = [self.token_to_id.get(t, self.SPECIAL_TOKENS["<unk>"]) for t in tokens]
 
        if add_special_tokens:
            ids = [self.SPECIAL_TOKENS["<bos>"]] + ids + [self.SPECIAL_TOKENS["<eos>"]]
 
        return ids
 
    def decode(self, ids: List[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs to text."""
        special_ids = set(self.SPECIAL_TOKENS.values()) if skip_special_tokens else set()
        tokens = [self.id_to_token.get(i, "<unk>") for i in ids if i not in special_ids]
 
        # Reconstruct text from BPE tokens
        text = " ".join(tokens)
        # Remove word boundary markers
        text = text.replace("</w> ", " ").replace("</w>", "")
        # Decode byte tokens
        text = self._decode_bytes(text)
 
        return text.strip()
 
    def _tokenize(self, text: str) -> List[str]:
        """Apply BPE merges to tokenize text."""
        # Start with byte-level tokens
        words = text.split()
        all_tokens = []
 
        for word in words:
            byte_toks = list(f"<byte_{b}>" for b in word.encode("utf-8"))
            if byte_toks:
                byte_toks[-1] = byte_toks[-1] + "</w>"
 
            # Apply merges
            for pair in self.merges:
                new_toks = []
                i = 0
                while i < len(byte_toks):
                    if i < len(byte_toks) - 1 and byte_toks[i] == pair[0] and byte_toks[i+1] == pair[1]:
                        new_toks.append(pair[0] + pair[1])
                        i += 2
                    else:
                        new_toks.append(byte_toks[i])
                        i += 1
                byte_toks = new_toks
 
            all_tokens.extend(byte_toks)
            all_tokens.append(" ")  # space between words
 
        return all_tokens[:-1] if all_tokens else all_tokens  # remove trailing space
 
    def _byte_encode(self, text: str, add_special: bool) -> List[int]:
        """Pure byte-level fallback encoding."""
        ids = [self.SPECIAL_TOKENS.get(f"<byte_{b}>",
               len(self.SPECIAL_TOKENS) + b) for b in text.encode("utf-8")]
        if add_special:
            ids = [self.SPECIAL_TOKENS["<bos>"]] + ids + [self.SPECIAL_TOKENS["<eos>"]]
        return ids
 
    def _decode_bytes(self, text: str) -> str:
        """Decode <byte_N> tokens back to characters."""
        def replace_byte(m):
            try:
                return bytes([int(m.group(1))]).decode("utf-8", errors="replace")
            except Exception:
                return "?"
        return re.sub(r"<byte_(\d+)>", replace_byte, text)
 
    # ── Conversation formatting ───────────────────────────────────
 
    def encode_conversation(self, messages: List[Dict[str, str]]) -> List[int]:
        """
        Encode a conversation in HELENA's format.
 
        Format:
            <sys> system content <user> user message <hele> response <eos>
        """
        ids = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                ids += [self.SPECIAL_TOKENS["<sys>"]] + self.encode(content, add_special_tokens=False)
            elif role == "user":
                ids += [self.SPECIAL_TOKENS["<user>"]] + self.encode(content, add_special_tokens=False)
            elif role == "assistant":
                ids += [self.SPECIAL_TOKENS["<hele>"]] + self.encode(content, add_special_tokens=False)
        ids.append(self.SPECIAL_TOKENS["<eos>"])
        return ids
 
    # ── Persistence ───────────────────────────────────────────────
 
    def save(self, path: str) -> None:
        """Save tokenizer to disk."""
        Path(path).mkdir(parents=True, exist_ok=True)
        data = {
            "vocab_size": self.vocab_size,
            "token_to_id": self.token_to_id,
            "merges": self.merges,
            "trained": self._trained,
        }
        with open(os.path.join(path, "tokenizer.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Tokenizer saved to {path}")
 
    @classmethod
    def load(cls, path: str) -> "HelenaTokenizer":
        """Load tokenizer from disk."""
        with open(os.path.join(path, "tokenizer.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        tok = cls(vocab_size=data["vocab_size"])
        tok.token_to_id = {k: int(v) for k, v in data["token_to_id"].items()}
        tok.id_to_token = {int(v): k for k, v in data["token_to_id"].items()}
        tok.merges = [tuple(m) for m in data["merges"]]
        tok._trained = data.get("trained", True)
        return tok
 
    def __len__(self) -> int:
        return len(self.token_to_id)
