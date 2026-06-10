"""Unified Memory Store for multi-agent knowledge sharing.

All AI agents connecting to the same Obsidian vault share one memory pool.
Memories are stored as structured Obsidian notes with rich metadata.

Directory structure:
    memories/
    ├── README.md              # Auto-generated index
    ├── codex/                 # Codex memories
    ├── claude/                # Claude memories
    ├── cursor/                # Cursor memories
    ├── shared/                # Merged/shared memories
    └── archive/               # Archived memories
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

# Known agent names for folder routing
_KNOWN_AGENTS = ("codex", "claude", "cursor", "user")

# Memory lifecycle constants
DECAY_DAYS = 30
MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 5
ARCHIVE_AFTER_DAYS = 90


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


def _agent_folder(agent: str) -> str:
    """Map agent name to its subfolder."""
    agent_lower = agent.lower().split(",")[0].strip()  # take first agent if merged
    if agent_lower in _KNOWN_AGENTS:
        return agent_lower
    return "shared"


class UnifiedMemoryStore:
    """Cross-agent unified memory system."""

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
        """Save a memory to the unified store.

        Memories are routed to agent-specific subfolders:
            memories/<agent>/mem-<hash>_<title>.md
        """
        now = datetime.now()
        content_hash = _content_hash(content)

        # Dedup
        existing = self._find_by_hash(content_hash)
        if existing:
            return self._update_existing(existing, content, agent, importance)

        if not title:
            title = content[:60].replace("\n", " ").strip()
            if len(content) > 60:
                title += "..."

        memory_id = f"{_MEMORY_PREFIX}{content_hash}"
        safe_title = _safe_title(title)
        agent_dir = _agent_folder(agent)
        filename = f"{memory_id}_{safe_title}"
        path = f"{self.folder}/{agent_dir}/{filename}"

        memory_tags = ["memory", category, agent_dir]
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

        # Update the index
        self._update_index()

        return {
            "memory_id": memory_id,
            "path": f"{path}.md",
            "title": title,
            "category": category,
            "agent": agent,
            "folder": agent_dir,
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
        """Search and retrieve memories from all agent folders."""
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
                    if agent and agent not in r.frontmatter.get("agent", ""):
                        continue
                    results.append(self._format_result(r.path, r.name, r.snippet, r.frontmatter, r.tags))
            else:
                notes = self.vault.list_notes(folder=folder, recursive=True)
                for note in notes[-limit * 2:]:
                    try:
                        parsed = self.vault.read_note(note["path"])
                    except (FileNotFoundError, OSError):
                        continue
                    if parsed.frontmatter.get("type") != "memory":
                        continue
                    if not include_archived and parsed.frontmatter.get("status") == "archived":
                        continue
                    if parsed.frontmatter.get("importance", 1) < min_importance:
                        continue
                    if category and parsed.frontmatter.get("category") != category:
                        continue
                    if agent and agent not in parsed.frontmatter.get("agent", ""):
                        continue
                    results.append(self._format_result(
                        note["path"], parsed.title, parsed.body[:200],
                        parsed.frontmatter, parsed.tags
                    ))

        results.sort(key=lambda r: (r.get("importance", 0), r.get("created", "")), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Update / Access
    # ------------------------------------------------------------------

    def access_memory(self, memory_id: str) -> dict[str, Any] | None:
        """Mark a memory as accessed."""
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
        """Update an existing memory."""
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
        self._update_index()
        return {"memory_id": memory_id, "updated": True}

    # ------------------------------------------------------------------
    # Delete / Archive
    # ------------------------------------------------------------------

    def forget_memory(self, path_or_id: str) -> bool:
        """Delete a memory by path or memory_id."""
        if path_or_id.startswith(_MEMORY_PREFIX):
            note = self._find_by_id(path_or_id)
            if note:
                result = self.vault.delete_note(note["path"])
                self._update_index()
                return result
            return False
        result = self.vault.delete_note(path_or_id)
        self._update_index()
        return result

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
        self._update_index()
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run_lifecycle(self) -> dict[str, Any]:
        """Run memory lifecycle: decay + archive."""
        now = datetime.now()
        decayed = 0
        archived = 0
        notes = self.vault.list_notes(folder=self.folder, recursive=True)
        for note_info in notes:
            try:
                parsed = self.vault.read_note(note_info["path"])
            except (FileNotFoundError, OSError):
                continue
            fm = parsed.frontmatter
            if fm.get("type") != "memory" or fm.get("status") == "archived":
                continue

            last_str = fm.get("last_accessed", fm.get("created"))
            if not last_str:
                continue
            try:
                last_accessed = datetime.fromisoformat(str(last_str))
            except (ValueError, TypeError):
                continue

            days_since = (now - last_accessed).days
            importance = fm.get("importance", 3)

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

            if days_since > ARCHIVE_AFTER_DAYS and importance <= MIN_IMPORTANCE:
                self.archive_memory(fm.get("memory_id", ""))
                archived += 1

        self._update_index()
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
        """Merge multiple memories into one, archive originals."""
        if len(memory_ids) < 2:
            raise ValueError("Need at least 2 memories to merge")

        sources = []
        for mid in memory_ids:
            note = self._find_by_id(mid)
            if note:
                sources.append({"id": mid, "path": note["path"], "title": note["name"]})

        if not sources:
            raise ValueError("No valid memories found to merge")

        result = self.save_memory(
            content=merged_content,
            title=title or f"Merged: {', '.join(s['title'][:20] for s in sources[:3])}",
            category="merged",
            importance=importance,
            agent=agent,
            related_memories=memory_ids,
        )

        for src in sources:
            self.archive_memory(src["id"])

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
    # Stats / Index
    # ------------------------------------------------------------------

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

    def _update_index(self) -> None:
        """Regenerate the memories/README.md index note."""
        try:
            self._ensure_folders()
            stats = self.get_stats()
            notes = self.vault.list_notes(folder=self.folder, recursive=True)

            # Group memories by agent folder
            by_folder: dict[str, list[dict]] = {}
            for note_info in notes:
                try:
                    parsed = self.vault.read_note(note_info["path"])
                except (FileNotFoundError, OSError):
                    continue
                fm = parsed.frontmatter
                if fm.get("type") != "memory":
                    continue
                # Determine folder from path
                # Normalize path separators for cross-platform
                rel = note_info["path"].replace("\\", "/").replace(f"{self.folder}/", "")
                parts = rel.split("/")
                folder = parts[0] if len(parts) > 1 else "root"
                if folder not in by_folder:
                    by_folder[folder] = []
                by_folder[folder].append({
                    "id": fm.get("memory_id", ""),
                    "title": parsed.title,
                    "agent": fm.get("agent", ""),
                    "category": fm.get("category", ""),
                    "importance": fm.get("importance", 0),
                    "created": fm.get("created", ""),
                    "status": fm.get("status", "active"),
                    "path": note_info["path"].replace(f"{self.folder}/", ""),
                })

            # Build markdown
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            lines = [
                "# Memory Index",
                f"> Auto-generated by obsidian-mcp | Updated: {now}",
                "",
                "---",
                "",
                "## Overview",
                "",
                f"- **Active memories:** {stats['active_memories']}",
                f"- **Archived:** {stats['archived_memories']}",
                f"- **By agent:** {', '.join(f'{k}({v})' for k, v in stats['by_agent'].items())}",
                f"- **By category:** {', '.join(f'{k}({v})' for k, v in stats['by_category'].items())}",
                "",
                "---",
                "",
            ]

            # Per-folder sections
            folder_order = ["codex", "claude", "cursor", "shared", "root", "archive"]
            folder_labels = {
                "codex": "Codex Memories",
                "claude": "Claude Desktop Memories",
                "cursor": "Cursor Memories",
                "shared": "Shared / Merged Memories",
                "root": "Unsorted Memories",
                "archive": "Archived Memories",
            }

            for folder in folder_order:
                mems = by_folder.get(folder, [])
                if not mems:
                    continue
                label = folder_labels.get(folder, folder.title())
                lines.append(f"## {label}")
                lines.append("")
                for m in sorted(mems, key=lambda x: x.get("created", ""), reverse=True):
                    imp = "*" * m["importance"] if m["importance"] else "-"
                    status_badge = " `[archived]`" if m["status"] == "archived" else ""
                    lines.append(
                        f"- [[{Path(m['path']).stem}]] "
                        f"{m['category']} | {m['agent']} | imp:{imp}{status_badge}"
                    )
                lines.append("")

            # Also list any folders we haven't covered
            for folder, mems in by_folder.items():
                if folder not in folder_order and mems:
                    lines.append(f"## {folder.title()} Memories")
                    lines.append("")
                    for m in sorted(mems, key=lambda x: x.get("created", ""), reverse=True):
                        imp = "*" * m["importance"] if m["importance"] else "-"
                        lines.append(
                            f"- [[{Path(m['path']).stem}]] "
                            f"{m['category']} | {m['agent']} | imp:{imp}"
                        )
                    lines.append("")

            index_content = "\n".join(lines)
            index_path = f"{self.folder}/README.md"
            try:
                self.vault.read_note(index_path)
                self.vault.update_note(index_path, content=index_content)
            except FileNotFoundError:
                self.vault.create_note(index_path, content=index_content)
        except Exception:
            pass  # Don't let index generation break memory operations

    def _ensure_folders(self) -> None:
        """Create agent subfolders if they don't exist."""
        for agent in ["codex", "claude", "cursor", "shared", "archive"]:
            folder_path = self.config.resolve_path(f"{self.folder}/{agent}")
            folder_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Find a memory by its content hash."""
        notes = self.vault.list_notes(folder=self.folder, recursive=True)
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
        if importance > existing["frontmatter"].get("importance", 0):
            updates["importance"] = importance
        existing_agents = existing["frontmatter"].get("agent", "unknown")
        if agent not in existing_agents:
            updates["agent"] = f"{existing_agents},{agent}"
        self.vault.update_note(existing["path"], frontmatter_updates=updates)
        self._update_index()
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
