"""Unified Memory Store for multi-agent knowledge sharing.

All AI agents connecting to the same Obsidian vault share one memory pool.
Memories are stored as structured Obsidian notes with rich metadata.

Features:
- Agent attribution: tracks which agent created each memory
- Deduplication: detects and merges similar memories
- Memory linking: memories reference each other forming a knowledge graph
- Importance decay: unused memories lose weight, important ones persist
- Unified search: any agent can find memories from all other agents
- Memory merging: combine scattered notes into consolidated knowledge
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .parser import build_frontmatter, parse_frontmatter, WIKILINK_RE
from .vault import Vault

# Memory note prefix for filename sorting
_MEMORY_PREFIX = "mem-"

# Memory lifecycle constants
DECAY_DAYS = 30          # importance drops by 1 after 30 days of no access
MIN_IMPORTANCE = 1       # floor
MAX_IMPORTANCE = 5       # ceiling
ARCHIVE_AFTER_DAYS = 90  # move to memories/archive/ after 90 days at min importance


def _content_hash(content: str) -> str:
    """Generate a short hash for dedup detection."""
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    return hashlib.md5(normalized.encode()).hexdigest()[:10]


def _safe_title(title: str, max_len: int = 60) -> str:
    """Sanitize a title for use as a filename."""
    safe = "".join(
        c if c.isalnum() or c in " -_" else "_"
        for c in title
    ).strip()
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip()
    return safe or "untitled"


class UnifiedMemoryStore:
    """Cross-agent unified memory system.

    Memories are Obsidian notes with this frontmatter schema:

        type: memory
        memory_id: mem-<hash>
        category: fact | task | insight | conversation | preference | rule
        agent: codex | claude | cursor | user | ...
        importance: 1-5
        access_count: int
        created: ISO datetime
        updated: ISO datetime
        last_accessed: ISO datetime
        content_hash: str (for dedup)
        tags: [memory, <category>, ...]
        related: [mem-xxx, mem-yyy, ...]   (links to other memories)
        merged_from: [mem-xxx, ...]         (if this memory was merged)
        status: active | archived | decayed
    """

    def __init__(self, config: ObsidianConfig, vault: Vault) -> None:
        self.config = config
        self.vault = vault
        self.folder = config.memory_folder
        self.archive_folder = f"{config.memory_folder}/archive"

    # ------------------------------------------------------------------
    # Save / Create
    # ------------------------------------------------------------------

    def save_memory(
        self,
        content: str,
        title: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        importance: int = 3,
        agent: str = "agent",
        related_notes: list[str] | None = None,
        related_memories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save a memory. Detects duplicates and merges if found.

        Args:
            content: Memory content
            title: Title (auto-generated if empty)
            category: fact/task/insight/conversation/preference/rule/general
            tags: Additional tags
            importance: 1-5
            agent: Which agent is saving (codex/claude/cursor/user)
            related_notes: Links to vault notes (wikilink names)
            related_memories: Links to other memory IDs (mem-xxx)
        """
        now = datetime.now()
        content_hash = _content_hash(content)

        # Dedup: check for existing memory with same content hash
        existing = self._find_by_hash(content_hash)
        if existing:
            return self._update_existing(existing, content, agent, importance)

        if not title:
            title = content[:60].replace("\n", " ").strip()
            if len(content) > 60:
                title += "..."

        memory_id = f"{_MEMORY_PREFIX}{content_hash}"
        safe_title = _safe_title(title)
        filename = f"{memory_id}_{safe_title}"
        path = f"{self.folder}/{filename}"

        memory_tags = ["memory", category]
        if tags:
            memory_tags.extend(tags)

        frontmatter = {
            "type": "memory",
            "memory_id": memory_id,
            "category": category,
            "agent": agent,
            "importance": min(max(importance, MIN_IMPORTANCE), MAX_IMPORTANCE),
            "access_count": 0,
            "created": now.isoformat(),
            "updated": now.isoformat(),
            "last_accessed": now.isoformat(),
            "content_hash": content_hash,
            "tags": memory_tags,
            "status": "active",
        }
        if related_memories:
            frontmatter["related"] = related_memories

        body = content
        if related_notes:
            links = " ".join(f"[[{n}]]" for n in related_notes)
            body += f"\n\n---\n**Related notes:** {links}"
        if related_memories:
            mem_links = " ".join(f"[[{m}]]" for m in related_memories)
            body += f"\n**Related memories:** {mem_links}"

        note = self.vault.create_note(path, content=body, frontmatter=frontmatter)
        return {
            "memory_id": memory_id,
            "path": f"{path}.md",
            "title": title,
            "category": category,
            "agent": agent,
            "importance": frontmatter["importance"],
            "dedup": False,
        }

    # ------------------------------------------------------------------
    # Recall / Search
    # ------------------------------------------------------------------

    def recall_memories(
        self,
        query: str | None = None,
        category: str | None = None,
        agent: str | None = None,
        min_importance: int = 1,
        include_archived: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search and retrieve memories.

        Args:
            query: Text search (None = list recent)
            category: Filter by category
            agent: Filter by creator agent
            min_importance: Minimum importance level
            include_archived: Include archived memories
            limit: Max results
        """
        from .search import SearchEngine
        engine = SearchEngine(self.config)
        results: list[dict[str, Any]] = []

        search_folders = [self.folder]
        if include_archived:
            search_folders.append(self.archive_folder)

        for folder in search_folders:
            if query:
                hits = engine.fulltext_search(query, folder=folder, limit=limit * 2)
                for r in hits:
                    if r.frontmatter.get("type") != "memory":
                        continue
                    if r.frontmatter.get("importance", 1) < min_importance:
                        continue
                    if category and r.frontmatter.get("category") != category:
                        continue
                    if agent and r.frontmatter.get("agent") != agent:
                        continue
                    results.append(self._format_result(r.path, r.name, r.snippet, r.frontmatter, r.tags))
            else:
                notes = self.vault.list_notes(folder=folder, recursive=False)
                for note in notes[-limit * 2:]:
                    try:
                        parsed = self.vault.read_note(note["path"])
                        if parsed.frontmatter.get("type") != "memory":
                            continue
                        if parsed.frontmatter.get("importance", 1) < min_importance:
                            continue
                        if category and parsed.frontmatter.get("category") != category:
                            continue
                        if agent and parsed.frontmatter.get("agent") != agent:
                            continue
                        results.append(self._format_result(
                            note["path"], parsed.title, parsed.body[:200],
                            parsed.frontmatter, parsed.tags
                        ))
                    except (FileNotFoundError, OSError):
                        continue

        results.sort(key=lambda r: (r.get("importance", 0), r.get("created", "")), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Update / Access
    # ------------------------------------------------------------------

    def access_memory(self, memory_id: str) -> dict[str, Any] | None:
        """Mark a memory as accessed (bumps access_count and last_accessed)."""
        note = self._find_by_id(memory_id)
        if not note:
            return None
        now = datetime.now().isoformat()
        self.vault.update_note(
            note["path"],
            frontmatter_updates={
                "access_count": note["frontmatter"].get("access_count", 0) + 1,
                "last_accessed": now,
            },
        )
        return {"memory_id": memory_id, "accessed": now}

    def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: int | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        agent: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an existing memory's content or metadata."""
        note = self._find_by_id(memory_id)
        if not note:
            return None
        updates: dict[str, Any] = {"updated": datetime.now().isoformat()}
        if importance is not None:
            updates["importance"] = min(max(importance, MIN_IMPORTANCE), MAX_IMPORTANCE)
        if category:
            updates["category"] = category
        if tags:
            existing_tags = note["frontmatter"].get("tags", ["memory"])
            updates["tags"] = list(set(existing_tags + tags))
        if agent:
            updates["agent"] = agent
        self.vault.update_note(note["path"], frontmatter_updates=updates)
        return {"memory_id": memory_id, "updated": True}

    # ------------------------------------------------------------------
    # Delete / Archive
    # ------------------------------------------------------------------

    def forget_memory(self, path_or_id: str) -> bool:
        """Delete a memory by path or memory_id."""
        if path_or_id.startswith(_MEMORY_PREFIX):
            note = self._find_by_id(path_or_id)
            if note:
                return self.vault.delete_note(note["path"])
            return False
        return self.vault.delete_note(path_or_id)

    def archive_memory(self, memory_id: str) -> bool:
        """Move a memory to the archive folder."""
        note = self._find_by_id(memory_id)
        if not note:
            return False
        src = note["path"]
        filename = Path(src).name
        dst = f"{self.archive_folder}/{filename}"
        self.vault.move_note(src.replace(".md", ""), dst.replace(".md", ""))
        self.vault.update_note(dst, frontmatter_updates={"status": "archived"})
        return True

    # ------------------------------------------------------------------
    # Lifecycle: decay & archive
    # ------------------------------------------------------------------

    def run_lifecycle(self) -> dict[str, Any]:
        """Run memory lifecycle maintenance.
        
        - Decay: reduce importance for memories not accessed recently
        - Archive: move low-importance old memories to archive
        
        Returns summary of actions taken.
        """
        now = datetime.now()
        decayed = 0
        archived = 0
        notes = self.vault.list_notes(folder=self.folder, recursive=False)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            fm = parsed.frontmatter
            if fm.get("type") != "memory" or fm.get("status") == "archived":
                continue

            # Parse last_accessed
            last_str = fm.get("last_accessed", fm.get("created"))
            if not last_str:
                continue
            try:
                last_accessed = datetime.fromisoformat(str(last_str))
            except (ValueError, TypeError):
                continue

            days_since = (now - last_accessed).days
            importance = fm.get("importance", 3)

            # Decay
            if days_since > DECAY_DAYS and importance > MIN_IMPORTANCE:
                new_imp = importance - 1
                self.vault.update_note(
                    note_info["path"],
                    frontmatter_updates={
                        "importance": new_imp,
                        "status": "decayed" if new_imp <= MIN_IMPORTANCE else "active",
                    },
                )
                decayed += 1
                importance = new_imp

            # Archive low-importance old memories
            if days_since > ARCHIVE_AFTER_DAYS and importance <= MIN_IMPORTANCE:
                self.archive_memory(fm.get("memory_id", ""))
                archived += 1

        return {"decayed": decayed, "archived": archived}

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge_memories(
        self,
        memory_ids: list[str],
        merged_content: str,
        title: str = "",
        agent: str = "agent",
        importance: int = 4,
    ) -> dict[str, Any]:
        """Merge multiple memories into one consolidated memory.
        
        The original memories are archived, and a new merged memory
        is created with references to the originals.
        """
        if len(memory_ids) < 2:
            raise ValueError("Need at least 2 memories to merge")

        sources = []
        for mid in memory_ids:
            note = self._find_by_id(mid)
            if note:
                sources.append({"id": mid, "path": note["path"], "title": note["name"]})

        if not sources:
            raise ValueError("No valid memories found to merge")

        # Save merged memory
        result = self.save_memory(
            content=merged_content,
            title=title or f"Merged: {', '.join(s['title'][:20] for s in sources[:3])}",
            category="merged",
            importance=importance,
            agent=agent,
            related_memories=memory_ids,
        )

        # Archive originals
        for src in sources:
            self.archive_memory(src["id"])

        # Tag the new memory as merged
        self.vault.update_note(
            result["path"],
            frontmatter_updates={"merged_from": memory_ids},
        )

        return {
            "merged": True,
            "new_memory_id": result["memory_id"],
            "merged_count": len(sources),
            "archived_sources": [s["id"] for s in sources],
        }

    # ------------------------------------------------------------------
    # Stats / Categories
    # ------------------------------------------------------------------

    def list_categories(self) -> list[dict[str, Any]]:
        """List all memory categories with counts."""
        cats: dict[str, int] = {}
        agents: dict[str, int] = {}
        notes = self.vault.list_notes(folder=self.folder, recursive=False)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            fm = parsed.frontmatter
            if fm.get("type") != "memory":
                continue
            cat = fm.get("category", "general")
            agent = fm.get("agent", "unknown")
            cats[cat] = cats.get(cat, 0) + 1
            agents[agent] = agents.get(agent, 0) + 1
        return [{"categories": cats, "agents": agents, "total": sum(cats.values())}]

    def get_stats(self) -> dict[str, Any]:
        """Get memory store statistics."""
        active = 0
        archived = 0
        by_agent: dict[str, int] = {}
        by_category: dict[str, int] = {}
        total_importance = 0
        notes = self.vault.list_notes(folder=self.folder, recursive=True)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            fm = parsed.frontmatter
            if fm.get("type") != "memory":
                continue
            status = fm.get("status", "active")
            if status == "archived":
                archived += 1
            else:
                active += 1
            agent = fm.get("agent", "unknown")
            by_agent[agent] = by_agent.get(agent, 0) + 1
            cat = fm.get("category", "general")
            by_category[cat] = by_category.get(cat, 0) + 1
            total_importance += fm.get("importance", 0)
        return {
            "active_memories": active,
            "archived_memories": archived,
            "total_memories": active + archived,
            "by_agent": by_agent,
            "by_category": by_category,
            "avg_importance": round(total_importance / max(active + archived, 1), 1),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Find a memory by its content hash."""
        notes = self.vault.list_notes(folder=self.folder, recursive=False)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            if parsed.frontmatter.get("content_hash") == content_hash:
                return {"path": note_info["path"], "name": parsed.title, "frontmatter": parsed.frontmatter}
        return None

    def _find_by_id(self, memory_id: str) -> dict[str, Any] | None:
        """Find a memory by its memory_id."""
        notes = self.vault.list_notes(folder=self.folder, recursive=True)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            if parsed.frontmatter.get("memory_id") == memory_id:
                return {"path": note_info["path"], "name": parsed.title, "frontmatter": parsed.frontmatter}
        return None

    def _update_existing(
        self, existing: dict[str, Any], new_content: str, agent: str, importance: int
    ) -> dict[str, Any]:
        """Update an existing memory (dedup path)."""
        now = datetime.now().isoformat()
        updates: dict[str, Any] = {
            "updated": now,
            "last_accessed": now,
            "access_count": existing["frontmatter"].get("access_count", 0) + 1,
        }
        # Keep higher importance
        if importance > existing["frontmatter"].get("importance", 0):
            updates["importance"] = importance
        # Track all contributing agents
        existing_agents = existing["frontmatter"].get("agent", "unknown")
        if agent not in existing_agents:
            updates["agent"] = f"{existing_agents},{agent}"
        self.vault.update_note(existing["path"], frontmatter_updates=updates)
        return {
            "memory_id": existing["frontmatter"].get("memory_id"),
            "path": existing["path"],
            "title": existing["name"],
            "category": existing["frontmatter"].get("category"),
            "agent": updates.get("agent", existing_agents),
            "importance": updates.get("importance", existing["frontmatter"].get("importance")),
            "dedup": True,
        }

    def _format_result(
        self, path: str, name: str, snippet: str,
        frontmatter: dict[str, Any], tags: list[str]
    ) -> dict[str, Any]:
        return {
            "memory_id": frontmatter.get("memory_id", ""),
            "path": path,
            "title": name,
            "snippet": snippet[:200],
            "category": frontmatter.get("category", ""),
            "agent": frontmatter.get("agent", ""),
            "importance": frontmatter.get("importance", 0),
            "access_count": frontmatter.get("access_count", 0),
            "created": frontmatter.get("created", ""),
            "last_accessed": frontmatter.get("last_accessed", ""),
            "status": frontmatter.get("status", "active"),
            "tags": tags,
        }
