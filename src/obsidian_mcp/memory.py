"""Memory/knowledge store for saving AI agent memories in Obsidian notes."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .parser import build_frontmatter, parse_frontmatter
from .vault import Vault


class MemoryStore:
    """Store and retrieve agent memories as Obsidian notes.
    
    Memories are stored as individual notes with frontmatter metadata
    including timestamps, categories, importance levels, and tags.
    """

    def __init__(self, config: ObsidianConfig, vault: Vault) -> None:
        self.config = config
        self.vault = vault
        self.folder = config.memory_folder

    def save_memory(
        self,
        content: str,
        title: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        importance: int = 3,
        source: str = "agent",
        related_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save a memory as an Obsidian note.
        
        Args:
            content: The memory content
            title: Title (auto-generated if empty)
            category: Memory category (general, conversation, fact, task, etc.)
            tags: Additional tags
            importance: 1-5 scale
            source: Where the memory came from
            related_notes: List of related note names for wikilinks
        """
        now = datetime.now()
        if not title:
            # Generate a title from content
            title = content[:50].replace("\n", " ").strip()
            if len(content) > 50:
                title += "..."

        # Sanitize title for filename
        safe_title = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in title
        ).strip()
        if not safe_title:
            safe_title = hashlib.md5(content.encode()).hexdigest()[:12]

        filename = f"{now.strftime('%Y%m%d-%H%M%S')}_{safe_title}"
        path = f"{self.folder}/{filename}"

        memory_tags = ["memory", category]
        if tags:
            memory_tags.extend(tags)

        frontmatter = {
            "type": "memory",
            "category": category,
            "importance": importance,
            "source": source,
            "created": now.isoformat(),
            "tags": memory_tags,
        }

        # Build body with related note links
        body = content
        if related_notes:
            links = " ".join(f"[[{n}]]" for n in related_notes)
            body += f"\n\n---\n**Related:** {links}"

        note = self.vault.create_note(
            path, content=body, frontmatter=frontmatter
        )
        return {
            "path": f"{path}.md",
            "title": title,
            "category": category,
            "importance": importance,
        }

    def recall_memories(
        self,
        query: str | None = None,
        category: str | None = None,
        min_importance: int = 1,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search and retrieve stored memories.
        
        Args:
            query: Text to search for
            category: Filter by category
            min_importance: Minimum importance level
            limit: Max results
        """
        from .search import SearchEngine

        engine = SearchEngine(self.config)
        results = []

        if query:
            # Search within memory folder
            search_results = engine.fulltext_search(
                query, folder=self.config.memory_folder, limit=limit * 2
            )
            for r in search_results:
                if r.frontmatter.get("importance", 1) < min_importance:
                    continue
                if category and r.frontmatter.get("category") != category:
                    continue
                results.append({
                    "path": r.path,
                    "title": r.name,
                    "snippet": r.snippet,
                    "category": r.frontmatter.get("category", ""),
                    "importance": r.frontmatter.get("importance", 0),
                    "created": r.frontmatter.get("created", ""),
                    "tags": r.tags,
                })
        else:
            # List recent memories
            notes = self.vault.list_notes(folder=self.config.memory_folder, recursive=False)
            for note in notes[-limit:]:
                try:
                    parsed = self.vault.read_note(note["path"])
                    if parsed.frontmatter.get("importance", 1) < min_importance:
                        continue
                    if category and parsed.frontmatter.get("category") != category:
                        continue
                    results.append({
                        "path": note["path"],
                        "title": parsed.title,
                        "category": parsed.frontmatter.get("category", ""),
                        "importance": parsed.frontmatter.get("importance", 0),
                        "created": parsed.frontmatter.get("created", ""),
                        "tags": parsed.tags,
                        "snippet": parsed.body[:200],
                    })
                except (FileNotFoundError, OSError):
                    continue

        # Sort by importance (descending) then by created date
        results.sort(
            key=lambda r: (r.get("importance", 0), r.get("created", "")),
            reverse=True,
        )
        return results[:limit]

    def forget_memory(self, path: str) -> bool:
        """Delete a stored memory."""
        return self.vault.delete_note(path)

    def list_categories(self) -> list[str]:
        """List all memory categories in use."""
        categories = set()
        notes = self.vault.list_notes(folder=self.config.memory_folder, recursive=False)
        for note in notes:
            try:
                parsed = self.vault.read_note(note["path"])
                cat = parsed.frontmatter.get("category")
                if cat:
                    categories.add(cat)
            except (FileNotFoundError, OSError):
                continue
        return sorted(categories)
