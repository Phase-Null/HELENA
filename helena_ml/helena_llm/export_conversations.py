"""
HELENA Conversation Exporter

Extracts conversation history from ChromaDB using the proper Python API
and saves as JSONL for training HELENA-Net.

Run from the HELENA project root:
    python -m helena_ml.helena_llm.export_conversations

Output: helena_memory/conversations.jsonl
"""
import json
import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional


def extract_from_chromadb(storage_path: str) -> List[Dict]:
    """Extract conversations using ChromaDB Python API."""
    conversations = []
    try:
        import chromadb
        client = chromadb.PersistentClient(path=storage_path)
        collections = client.list_collections()
        print(f"Found {len(collections)} ChromaDB collections")

        for collection in collections:
            try:
                results = collection.get(include=["documents", "metadatas"])
                docs = results.get("documents") or []
                print(f"  Collection '{collection.name}': {len(docs)} documents")
                for doc in docs:
                    if not doc:
                        continue
                    conv = parse_conversation_text(doc)
                    if conv:
                        conversations.append(conv)
            except Exception as e:
                print(f"  Failed to read collection {collection.name}: {e}")

    except ImportError:
        print("ChromaDB not installed — skipping")
    except Exception as e:
        print(f"ChromaDB extraction failed: {e}")

    print(f"Extracted {len(conversations)} conversations from ChromaDB")
    return conversations


def parse_conversation_text(text: str) -> Optional[Dict]:
    """Parse a conversation text block into messages format."""
    messages = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("User:"):
            content = line[5:].strip()
            if content:
                messages.append({"role": "user", "content": content})
        elif line.startswith("HELENA:"):
            content = line[7:].strip()
            if content:
                messages.append({"role": "assistant", "content": content})
    if len(messages) >= 2:
        return {"messages": messages}
    return None


def extract_from_log(log_path: str) -> List[Dict]:
    """Extract conversations from HELENA's user.log."""
    conversations = []
    current_conv = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "User:" in line or "HELENA:" in line:
                    match = re.search(r"(User:|HELENA:)\s*(.+)", line)
                    if match:
                        role_marker = match.group(1)
                        content = match.group(2).strip()
                        if role_marker == "User:":
                            if current_conv:
                                if len(current_conv) >= 2:
                                    conversations.append({"messages": current_conv})
                                current_conv = []
                            current_conv.append({"role": "user", "content": content})
                        elif role_marker == "HELENA:" and current_conv:
                            current_conv.append({"role": "assistant", "content": content})
        if len(current_conv) >= 2:
            conversations.append({"messages": current_conv})
        print(f"Extracted {len(conversations)} conversations from log")
    except Exception as e:
        print(f"Log extraction failed: {e}")
    return conversations


def export_conversations(
    helena_root: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    if helena_root is None:
        helena_root = str(Path(__file__).resolve().parent.parent.parent)

    root = Path(helena_root)
    memory_dir = root / "helena_memory"
    memory_dir.mkdir(exist_ok=True)

    if output_path is None:
        output_path = str(memory_dir / "conversations.jsonl")

    all_conversations = []

    # Source 1: ChromaDB via Python API
    all_conversations.extend(extract_from_chromadb(str(memory_dir)))

    # Source 2: user.log
    user_log = root / "logs" / "user.log"
    if user_log.exists():
        all_conversations.extend(extract_from_log(str(user_log)))

    # Deduplicate
    seen = set()
    unique = []
    for conv in all_conversations:
        key = json.dumps(conv, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(conv)

    with open(output_path, "w", encoding="utf-8") as f:
        for conv in unique:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    print(f"Exported {len(unique)} unique conversations to {output_path}")
    return output_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export HELENA conversations for training")
    parser.add_argument("--root", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    path = export_conversations(helena_root=args.root, output_path=args.output)
    print(f"Done. Run training with: python -m helena_ml.helena_llm.train --config nano")


if __name__ == "__main__":
    main()
