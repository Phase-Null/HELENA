"""
NODE Reader — loads, parses, and indexes the Obsidian vault.

Capabilities:
  - Load all markdown notes from the NODE vault
  - Parse frontmatter (YAML between --- markers)
  - Resolve wikilinks ([[Note Name]]) to actual note paths
  - Extract Obsidian callouts (> [!type] content)
  - Search notes by keyword, tag, or section
  - Export note content as training data (conversation format)
  - List all tags, all notes, and the vault graph
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class NodeNote:
    """A single note in the NODE vault."""
    path: str                     # Relative path from vault root (e.g. "Architecture/HELENA-Net Model")
    title: str                    # Note title (from filename or frontmatter)
    content: str                  # Raw markdown content (after frontmatter)
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    wikilinks: List[str] = field(default_factory=list)
    callouts: List[Dict[str, str]] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)  # headings


class NodeReader:
    """Read and query the NODE Obsidian vault."""

    # ── Init ───────────────────────────────────────────────────────

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            # Default: look for NODE/ in the project root
            # Walk up from this file's location to find the project root
            this_dir = Path(__file__).resolve().parent
            for parent in [this_dir.parent, *this_dir.parents]:
                candidate = parent / "NODE"
                if candidate.is_dir() and (candidate / "Home.md").exists():
                    vault_path = str(candidate)
                    break
            if vault_path is None:
                vault_path = str(Path(__file__).resolve().parent.parent.parent / "NODE")

        self.vault_path = Path(vault_path).resolve()
        self.notes: Dict[str, NodeNote] = {}      # keyed by relative path (no .md)
        self._tag_index: Dict[str, List[str]] = defaultdict(list)
        self._section_index: Dict[str, List[str]] = defaultdict(list)
        self._loaded = False

    # ── Loading ────────────────────────────────────────────────────

    def load(self) -> int:
        """Load all markdown notes from the vault. Returns count of notes loaded."""
        count = 0
        for md_file in self.vault_path.rglob("*.md"):
            # Skip .obsidian directory
            if ".obsidian" in md_file.parts:
                continue

            rel_path = str(md_file.relative_to(self.vault_path))
            # Remove .md extension for the key
            note_key = rel_path[:-3] if rel_path.endswith(".md") else rel_path

            try:
                raw = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            frontmatter, content = self._parse_frontmatter(raw)
            title = md_file.stem
            if frontmatter and "title" in frontmatter:
                title = frontmatter["title"]

            tags = frontmatter.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]

            wikilinks = self._extract_wikilinks(content)
            callouts = self._extract_callouts(content)
            sections = self._extract_sections(content)

            note = NodeNote(
                path=note_key,
                title=title,
                content=content,
                frontmatter=frontmatter,
                tags=tags,
                wikilinks=wikilinks,
                callouts=callouts,
                sections=sections,
            )
            self.notes[note_key] = note
            count += 1

            # Build indexes
            for tag in tags:
                self._tag_index[tag].append(note_key)
            for section in sections:
                self._section_index[section.lower()].append(note_key)

        self._loaded = True
        return count

    # ── Parsing ────────────────────────────────────────────────────

    @staticmethod
    def _parse_frontmatter(raw: str) -> Tuple[Dict[str, Any], str]:
        """Split YAML frontmatter from content."""
        if not raw.startswith("---"):
            return {}, raw

        # Find the closing ---
        end = raw.find("---", 3)
        if end < 0:
            return {}, raw

        yaml_text = raw[3:end].strip()
        content = raw[end + 3:].strip()

        try:
            fm = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError:
            fm = {}

        return fm, content

    @staticmethod
    def _extract_wikilinks(content: str) -> List[str]:
        """Extract [[Note Name]] wikilinks from content."""
        return re.findall(r'\[\[([^\]]+)\]\]', content)

    @staticmethod
    def _extract_callouts(content: str) -> List[Dict[str, str]]:
        """Extract Obsidian callouts (> [!type] title | content)."""
        callouts = []
        # Match: > [!type] optional title
        #         > continuation lines
        pattern = re.compile(
            r'>\s*\[!(\w+)\]\s*(.*?)\n((?:>\s*.*?\n)*)',
            re.MULTILINE
        )
        for m in pattern.finditer(content):
            callout_type = m.group(1).lower()
            title = m.group(2).strip()
            body_lines = m.group(3).strip()
            # Remove leading '> ' from body lines
            body = re.sub(r'^>\s*', '', body_lines, flags=re.MULTILINE)
            callouts.append({
                "type": callout_type,
                "title": title,
                "body": body.strip(),
            })
        return callouts

    @staticmethod
    def _extract_sections(content: str) -> List[str]:
        """Extract ## headings from content."""
        return re.findall(r'^##\s+(.+)$', content, re.MULTILINE)

    # ── Query ──────────────────────────────────────────────────────

    def get_note(self, note_key: str) -> Optional[NodeNote]:
        """Get a note by its relative path (without .md extension)."""
        if not self._loaded:
            self.load()
        # Try exact match first
        if note_key in self.notes:
            return self.notes[note_key]
        # Try adding .md
        alt = note_key + ".md"
        if alt in self.notes:
            return self.notes[alt]
        # Try title match (case-insensitive)
        lower = note_key.lower()
        for key, note in self.notes.items():
            if note.title.lower() == lower:
                return note
        # Try fuzzy: last part of path
        stem = Path(note_key).stem.lower() if "/" in note_key else note_key.lower()
        for key, note in self.notes.items():
            if Path(key).stem.lower() == stem:
                return note
        return None

    def search(self, query: str, limit: int = 20) -> List[NodeNote]:
        """Search notes by keyword (matches in title, content, tags, sections)."""
        if not self._loaded:
            self.load()

        query_lower = query.lower()
        results: List[Tuple[int, NodeNote]] = []

        for key, note in self.notes.items():
            score = 0
            # Title match (highest weight)
            if query_lower in note.title.lower():
                score += 10
            # Tag match
            for tag in note.tags:
                if query_lower in tag.lower():
                    score += 5
            # Section heading match
            for section in note.sections:
                if query_lower in section.lower():
                    score += 3
            # Content match
            if query_lower in note.content.lower():
                score += 1

            if score > 0:
                results.append((score, note))

        # Sort by score descending
        results.sort(key=lambda x: -x[0])
        return [note for _, note in results[:limit]]

    def get_all_tags(self) -> Dict[str, List[str]]:
        """Return tag → [note_keys] index."""
        if not self._loaded:
            self.load()
        return dict(self._tag_index)

    def get_all_notes(self) -> List[str]:
        """Return all note keys."""
        if not self._loaded:
            self.load()
        return sorted(self.notes.keys())

    def get_vault_graph(self) -> Dict[str, List[str]]:
        """Return wikilink graph: note_key → [linked_note_keys]."""
        if not self._loaded:
            self.load()
        graph = {}
        for key, note in self.notes.items():
            resolved = []
            for link in note.wikilinks:
                # Try to resolve the wikilink to an actual note key
                target = self.get_note(link)
                if target:
                    resolved.append(target.path)
            graph[key] = resolved
        return graph

    # ── Export for Training ─────────────────────────────────────────

    def export_training_conversations(
        self,
        categories: Optional[List[str]] = None,
        max_per_note: int = 5,
    ) -> List[Dict[str, Any]]:
        """Export vault notes as HELENA-voice training conversations.

        Each note is converted into one or more conversation-format examples
        suitable for inclusion in the training dataset. The assistant responses
        are written in HELENA's voice, drawing directly from the vault content.

        Args:
            categories: Only export from these vault sections
                        (e.g. ["Architecture", "AEGIS"])
            max_per_note: Max conversations per note (sections create separate convs)

        Returns:
            List of {"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}
        """
        if not self._loaded:
            self.load()

        convs = []
        for key, note in self.notes.items():
            # Filter by category
            if categories:
                note_section = key.split("/")[0] if "/" in key else ""
                if note_section not in categories:
                    continue

            # Skip templates
            if key.startswith("_templates"):
                continue

            # Generate Q&A pairs from each section
            # For each ## heading, create a question asking about that topic
            # and an answer drawn from the section content
            section_content = self._split_by_sections(note.content)

            for heading, body in section_content[:max_per_note]:
                if not body.strip() or len(body.strip()) < 50:
                    continue

                # Generate a natural question
                question = self._generate_question(note.title, heading)

                # Format the answer in HELENA's voice
                answer = self._format_helena_response(note.title, heading, body)

                convs.append({
                    "messages": [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": answer},
                    ]
                })

        return convs

    @staticmethod
    def _split_by_sections(content: str) -> List[Tuple[str, str]]:
        """Split content into (heading, body) pairs."""
        sections = []
        # Split on ## headings
        parts = re.split(r'^##\s+(.+)$', content, flags=re.MULTILINE)
        # parts[0] is content before first heading, then alternating heading/body
        for i in range(1, len(parts), 2):
            heading = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            sections.append((heading.strip(), body.strip()))

        # If no sections found, use the whole content
        if not sections and content.strip():
            sections.append(("Overview", content.strip()))

        return sections

    @staticmethod
    def _generate_question(note_title: str, section_heading: str) -> str:
        """Generate a natural user question for a section."""
        # Map section headings to question patterns
        heading_lower = section_heading.lower()

        if heading_lower in ["overview", "overview"]:
            return f"Tell me about {note_title}."
        elif "architecture" in heading_lower or "design" in heading_lower:
            return f"How is {note_title} designed? What's the architecture?"
        elif "config" in heading_lower or "parameters" in heading_lower or "settings" in heading_lower:
            return f"What are the configuration options for {note_title}?"
        elif "bug" in heading_lower or "fix" in heading_lower or "fixes" in heading_lower:
            return f"What bugs have been found in {note_title} and how were they fixed?"
        elif "security" in heading_lower or "threat" in heading_lower or "aegis" in heading_lower:
            return f"How does {note_title} handle security?"
        elif "training" in heading_lower or "dataset" in heading_lower:
            return f"How does {note_title} training work? What's the dataset like?"
        elif "emotion" in heading_lower or "personality" in heading_lower:
            return f"How does {note_title}'s emotion system work?"
        elif "memory" in heading_lower:
            return f"How does {note_title} manage memory and recall?"
        else:
            return f"Can you explain the {section_heading} aspect of {note_title}?"

    @staticmethod
    def _format_helena_response(note_title: str, heading: str, body: str) -> str:
        """Format a vault section as a HELENA-voice response."""
        # Truncate very long bodies
        if len(body) > 1500:
            body = body[:1500] + "..."

        # Add HELENA's voice markers
        intro = f"As HELENA, I can tell you about the {heading} of {note_title}. "

        # Clean up markdown artifacts for natural language
        cleaned = re.sub(r'\[\[([^\]]+)\]\]', r'\1', body)  # wikilinks → plain text
        cleaned = re.sub(r'>\s*\[!\w+\]\s*', '', cleaned)     # remove callout markers
        cleaned = re.sub(r'^>\s*', '', cleaned, flags=re.MULTILINE)  # unquote callout lines
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)        # inline code → plain text

        return intro + cleaned.strip()

    # ── Stats ──────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return vault statistics."""
        if not self._loaded:
            self.load()

        total_chars = sum(len(n.content) for n in self.notes.values())
        total_tags = len(self._tag_index)

        return {
            "vault_path": str(self.vault_path),
            "total_notes": len(self.notes),
            "total_chars": total_chars,
            "total_tags": total_tags,
            "sections": list(set(
                k.split("/")[0] for k in self.notes.keys() if "/" in k
            )),
        }
