"""
HELENA Conversation Exporter
 
Extracts conversation history from ChromaDB and saves as JSONL
for training HELENA-Net.
 
Run from the HELENA project root:
    python -m helena_ml.helena_llm.export_conversations
 
Output: helena_memory/conversations.jsonl
"""
import json
import sqlite3
import re
import os
from pathlib import Path
from typing import List, Dict, Optional
 
 
def extract_from_chromadb(db_path: str) -> List[Dict]:
    """
    Extract conversation pairs from ChromaDB SQLite.
 
    ChromaDB stores conversation content as metadata.
    We look for entries with 'User:' and 'HELENA:' markers.
    """
    conversations = []
 
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
 
        # Try to find conversation content
        # ChromaDB schema varies by version — try multiple approaches
        try:
            cursor.execute("""
                SELECT string_value FROM embedding_metadata
                WHERE key = 'content'
                ORDER BY rowid
            """)
            rows = cursor.fetchall()
        except Exception:
            try:
                cursor.execute("SELECT document FROM embeddings LIMIT 10000")
                rows = cursor.fetchall()
            except Exception:
                rows = []
 
        conn.close()
 
        for (content,) in rows:
            if not content:
                continue
            conv = parse_conversation_text(content)
            if conv:
                conversations.append(conv)
 
        print(f"Extracted {len(conversations)} conversations from ChromaDB")
 
    except Exception as e:
        print(f"ChromaDB extraction failed: {e}")
 
    return conversations
 
 
def parse_conversation_text(text: str) -> Optional[Dict]:
    """
    Parse a conversation text block into messages format.
 
    Expected format:
        User: hello
        HELENA: hi there
    """
    messages = []
    lines = text.strip().split("\n")
 
    for line in lines:
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
 
 
def export_conversations(
    helena_root: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """
    Export all available conversations to JSONL.
 
    Sources checked in order:
    1. helena_memory/chroma.sqlite3 (ChromaDB)
    2. logs/user.log (if conversations logged there)
 
    Returns path to output file.
    """
    if helena_root is None:
        helena_root = str(Path(__file__).resolve().parent.parent.parent)
 
    root = Path(helena_root)
    memory_dir = root / "helena_memory"
    memory_dir.mkdir(exist_ok=True)
 
    if output_path is None:
        output_path = str(memory_dir / "conversations.jsonl")
 
    all_conversations = []
 
    # Source 1: ChromaDB
    chroma_path = memory_dir / "chroma.sqlite3"
    if chroma_path.exists():
        convs = extract_from_chromadb(str(chroma_path))
        all_conversations.extend(convs)
    else:
        print(f"ChromaDB not found at {chroma_path}")
 
    # Source 2: user.log (if it contains conversation data)
    user_log = root / "logs" / "user.log"
    if user_log.exists():
        convs = extract_from_log(str(user_log))
        all_conversations.extend(convs)
 
    # Deduplicate by content hash
    seen = set()
    unique = []
    for conv in all_conversations:
        key = json.dumps(conv, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(conv)
 
    # Write JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for conv in unique:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")
 
    print(f"Exported {len(unique)} unique conversations to {output_path}")
    return output_path
 
 
def extract_from_log(log_path: str) -> List[Dict]:
    """Extract conversations from HELENA's user.log."""
    conversations = []
    current_conv = []
 
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Look for conversation markers in log entries
                if "User:" in line or "HELENA:" in line:
                    # Extract the message part after the log timestamp
                    match = re.search(r"(User:|HELENA:)\s*(.+)", line)
                    if match:
                        role_marker = match.group(1)
                        content = match.group(2).strip()
                        if role_marker == "User:":
                            if current_conv:
                                # New conversation started — save previous
                                if len(current_conv) >= 2:
                                    conversations.append({"messages": current_conv})
                                current_conv = []
                            current_conv.append({"role": "user", "content": content})
                        elif role_marker == "HELENA:" and current_conv:
                            current_conv.append({"role": "assistant", "content": content})
 
        # Save last conversation
        if len(current_conv) >= 2:
            conversations.append({"messages": current_conv})
 
        print(f"Extracted {len(conversations)} conversations from log")
 
    except Exception as e:
        print(f"Log extraction failed: {e}")
 
    return conversations
 
 
def main():
    """Export conversations from CLI."""
    import argparse
    parser = argparse.ArgumentParser(description="Export HELENA conversations for training")
    parser.add_argument("--root", default=None, help="HELENA project root")
    parser.add_argument("--output", default=None, help="Output JSONL path")
    args = parser.parse_args()
 
    path = export_conversations(helena_root=args.root, output_path=args.output)
    print(f"Done. Training data at: {path}")
    print(f"Run training with: python -m helena_ml.helena_llm.train --config nano")
 
 
if __name__ == "__main__":
    main()
 
