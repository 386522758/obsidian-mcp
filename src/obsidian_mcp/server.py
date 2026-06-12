#!/usr/bin/env python3
"""Obsidian MCP Server.

Exposes Obsidian vault operations as MCP tools for AI agents.
Supports both direct file access and the Obsidian Local REST API plugin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

from .config import ObsidianConfig
from .daily import DailyNotesManager
from .memory import UnifiedMemoryStore
from .parser import make_wikilink
from .rest_api import ObsidianRestAPI
from .search import SearchEngine
from .templates import TemplateManager
from .vault import Vault

logger = logging.getLogger("obsidian-mcp")


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _text(content: str) -> list[TextContent]:
    return [TextContent(type="text", text=content)]


def _json_text(data: Any) -> list[TextContent]:
    return _text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _error(message: str, **extra: Any) -> list[TextContent]:
    return _json_text({"error": message, **extra})


def _parse_json(value: str, param_name: str) -> Any:
    """Parse a JSON string; raise ValueError with a clear message on failure."""
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for '{param_name}': {exc}") from exc


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ObsidianMCPServer:
    """MCP Server exposing Obsidian vault tools."""

    def __init__(self) -> None:
        self.server = FastMCP("obsidian-mcp")
        self.config: ObsidianConfig | None = None
        self.vault: Vault | None = None
        self.search: SearchEngine | None = None
        self.rest_api: ObsidianRestAPI | None = None
        self.templates: TemplateManager | None = None
        self.daily: DailyNotesManager | None = None
        self.memory: UnifiedMemoryStore | None = None
        self._setup_done = False

    def _ensure_setup(self) -> None:
        """Lazy initialisation from environment variables."""
        if self._setup_done:
            return
        self.config = ObsidianConfig.from_env()
        self.vault = Vault(self.config)
        self.search = SearchEngine(self.config)
        self.templates = TemplateManager(self.config, self.vault)
        self.daily = DailyNotesManager(self.config, self.vault)
        self.memory = UnifiedMemoryStore(self.config, self.vault)
        self.memory._ensure_folders()
        if self.config.rest_api_enabled:
            self.rest_api = ObsidianRestAPI(self.config)
        self._setup_done = True

    # ==================================================================
    # Tool registration
    # ==================================================================

    def register_tools(self) -> None:
        """Register all MCP tools."""

        # ----------------------------------------------------------
        # Note CRUD
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_read_note(path: str) -> list[TextContent]:
            """Read and parse an Obsidian note.

            Returns the note content along with parsed frontmatter,
            wikilinks, tags, and metadata.

            Args:
                path: Vault-relative path to the note (e.g. "folder/My Note.md")
            """
            self._ensure_setup()
            try:
                note = self.vault.read_note(path)
                return _json_text({
                    "path": path,
                    "title": note.title,
                    "content": note.content,
                    "body": note.body,
                    "frontmatter": note.frontmatter,
                    "tags": note.tags,
                    "wikilinks": note.wikilinks,
                    "embeds": note.embeds,
                    "callouts": note.callouts,
                    "modified": note.modified.isoformat() if note.modified else None,
                })
            except FileNotFoundError as exc:
                return _error(str(exc), path=path)
            except ValueError as exc:
                return _error(str(exc), path=path)

        @self.server.tool()
        async def obsidian_create_note(
            path: str,
            content: str = "",
            frontmatter: str = "{}",
            overwrite: bool = False,
        ) -> list[TextContent]:
            """Create a new Obsidian note.

            Args:
                path: Vault-relative path for the new note
                content: Body content (markdown)
                frontmatter: JSON string of frontmatter metadata (e.g. '{"tags": ["python"]}')
                overwrite: Whether to overwrite if a note already exists at this path
            """
            self._ensure_setup()
            try:
                fm = _parse_json(frontmatter, "frontmatter") if frontmatter not in ("", "{}") else None
                note = self.vault.create_note(path, content=content, frontmatter=fm, overwrite=overwrite)
                return _json_text({"status": "created", "path": path, "title": note.title})
            except FileExistsError as exc:
                return _error(str(exc), path=path)
            except (ValueError, FileNotFoundError) as exc:
                return _error(str(exc), path=path)

        @self.server.tool()
        async def obsidian_update_note(
            path: str,
            content: str | None = None,
            frontmatter: str | None = None,
            append: bool = False,
        ) -> list[TextContent]:
            """Update an existing Obsidian note.

            Args:
                path: Vault-relative path to the note
                content: New content (replaces body unless append=True)
                frontmatter: JSON string of frontmatter fields to update/merge
                append: If true, append content to end of note instead of replacing
            """
            self._ensure_setup()
            try:
                fm_updates = _parse_json(frontmatter, "frontmatter") if frontmatter else None
                note = self.vault.update_note(path, content=content, frontmatter_updates=fm_updates, append=append)
                return _json_text({"status": "updated", "path": path, "title": note.title})
            except FileNotFoundError as exc:
                return _error(str(exc), path=path)
            except ValueError as exc:
                return _error(str(exc), path=path)

        @self.server.tool()
        async def obsidian_delete_note(path: str) -> list[TextContent]:
            """Delete an Obsidian note.

            Args:
                path: Vault-relative path to the note to delete
            """
            self._ensure_setup()
            try:
                self.vault.delete_note(path)
                return _json_text({"status": "deleted", "path": path})
            except FileNotFoundError as exc:
                return _error(str(exc), path=path)
            except ValueError as exc:
                return _error(str(exc), path=path)

        @self.server.tool()
        async def obsidian_move_note(source: str, destination: str) -> list[TextContent]:
            """Move or rename an Obsidian note.

            Args:
                source: Current vault-relative path
                destination: New vault-relative path
            """
            self._ensure_setup()
            try:
                new_path = self.vault.move_note(source, destination)
                return _json_text({"status": "moved", "from": source, "to": new_path})
            except (FileNotFoundError, FileExistsError, ValueError) as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Listing & navigation
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_list_notes(
            folder: str = "",
            recursive: bool = True,
        ) -> list[TextContent]:
            """List all notes in the vault or a specific folder.

            Args:
                folder: Vault-relative folder path (empty = entire vault)
                recursive: Whether to include notes in subfolders
            """
            self._ensure_setup()
            try:
                notes = self.vault.list_notes(folder=folder, recursive=recursive)
                return _json_text({"count": len(notes), "notes": notes})
            except (FileNotFoundError, ValueError) as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_list_folders(folder: str = "") -> list[TextContent]:
            """List subdirectories in a vault folder.

            Args:
                folder: Parent folder (empty = vault root)
            """
            self._ensure_setup()
            try:
                folders = self.vault.list_folders(folder=folder)
                return _json_text({"folders": folders})
            except (FileNotFoundError, ValueError) as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_get_backlinks(note_name: str) -> list[TextContent]:
            """Find all notes that link to a given note via wikilinks.

            Args:
                note_name: The note name (without .md) to find backlinks for
            """
            self._ensure_setup()
            try:
                backlinks = self.vault.get_backlinks(note_name)
                return _json_text({"note": note_name, "backlinks": backlinks})
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_get_graph(limit: int = 500) -> list[TextContent]:
            """Get the vault's link graph showing wikilink relationships between notes.

            Args:
                limit: Maximum number of nodes to include (default 500, use 0 for all)
            """
            self._ensure_setup()
            try:
                graph = self.vault.get_graph()
                if limit > 0 and len(graph) > limit:
                    # Keep the most-connected nodes
                    graph = dict(
                        sorted(graph.items(), key=lambda kv: len(kv[1]), reverse=True)[:limit]
                    )
                return _json_text({"nodes": len(graph), "graph": graph})
            except ValueError as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Search
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_search(
            query: str,
            folder: str = "",
            limit: int = 20,
            case_sensitive: bool = False,
        ) -> list[TextContent]:
            """Full-text search across all notes in the vault.

            Supports +term for must-have and -term for exclusion.

            Args:
                query: Search query (e.g. "python 函数" or "+machine -learning")
                folder: Limit search to a specific folder
                limit: Maximum number of results
                case_sensitive: Whether the search is case-sensitive
            """
            self._ensure_setup()
            try:
                results = self.search.fulltext_search(
                    query, folder=folder, limit=limit, case_sensitive=case_sensitive
                )
                return _json_text({
                    "query": query,
                    "count": len(results),
                    "results": [
                        {
                            "path": r.path,
                            "name": r.name,
                            "score": r.score,
                            "snippet": r.snippet,
                            "tags": r.tags,
                        }
                        for r in results
                    ],
                })
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_search_by_tag(tag: str, limit: int = 50) -> list[TextContent]:
            """Find all notes with a specific tag.

            Args:
                tag: Tag to search for (with or without #)
                limit: Maximum results
            """
            self._ensure_setup()
            try:
                results = self.search.tag_search(tag, limit=limit)
                return _json_text({
                    "tag": tag,
                    "count": len(results),
                    "results": [{"path": r.path, "name": r.name, "tags": r.tags} for r in results],
                })
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_search_by_metadata(
            key: str,
            value: str | None = None,
            limit: int = 50,
        ) -> list[TextContent]:
            """Search notes by frontmatter metadata key/value.

            Args:
                key: Frontmatter key to filter on (e.g. "status", "type")
                value: Optional value to match (omit to find all notes with this key)
                limit: Maximum results
            """
            self._ensure_setup()
            try:
                results = self.search.metadata_search(key, value=value, limit=limit)
                return _json_text({
                    "key": key,
                    "value": value,
                    "count": len(results),
                    "results": [
                        {"path": r.path, "name": r.name, "frontmatter": r.frontmatter}
                        for r in results
                    ],
                })
            except ValueError as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Frontmatter helpers
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_update_frontmatter(
            path: str,
            metadata: str,
        ) -> list[TextContent]:
            """Update frontmatter fields of a note (merge, not replace).

            Args:
                path: Vault-relative path to the note
                metadata: JSON string of fields to update (e.g. '{"status": "done", "rating": 5}')
            """
            self._ensure_setup()
            try:
                updates = _parse_json(metadata, "metadata")
                note = self.vault.update_note(path, frontmatter_updates=updates)
                return _json_text({"status": "updated", "path": path, "frontmatter": note.frontmatter})
            except FileNotFoundError as exc:
                return _error(str(exc), path=path)
            except ValueError as exc:
                return _error(str(exc), path=path)

        # ----------------------------------------------------------
        # Wikilink helpers
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_create_link(
            target: str,
            display: str | None = None,
        ) -> list[TextContent]:
            """Create an Obsidian wikilink string.

            Args:
                target: Note name or path to link to
                display: Optional display text (omit to use the note name)
            """
            try:
                link = make_wikilink(target, display)
                return _text(link)
            except ValueError as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Templates
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_list_templates() -> list[TextContent]:
            """List available Obsidian templates."""
            self._ensure_setup()
            try:
                templates = self.templates.list_templates()
                return _json_text({"count": len(templates), "templates": templates})
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_apply_template(
            template: str,
            note_path: str,
            variables: str = "{}",
        ) -> list[TextContent]:
            """Create a new note from a template with variable substitution.

            Template variables use {{variable}} syntax.
            Built-in variables: {{date}}, {{time}}, {{datetime}}, {{year}}, {{month}}, {{day}}, {{weekday}}.

            Args:
                template: Template name (without .md)
                note_path: Vault-relative path for the new note
                variables: JSON string of custom variables (e.g. '{"title": "My Note"}')
            """
            self._ensure_setup()
            try:
                vars_dict = _parse_json(variables, "variables") if variables not in ("", "{}") else None
                result = self.templates.create_from_template(template, note_path, variables=vars_dict)
                return _json_text(result)
            except (FileNotFoundError, FileExistsError, ValueError) as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Daily notes
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_get_daily_note(date: str | None = None) -> list[TextContent]:
            """Get or create a daily note.

            Args:
                date: Date in YYYY-MM-DD format (defaults to today)
            """
            self._ensure_setup()
            try:
                if date:
                    from datetime import datetime as dt
                    target = dt.strptime(date, "%Y-%m-%d")
                    note = self.daily.get_daily(target)
                else:
                    note = self.daily.get_today()
                return _json_text({
                    "path": str(note.file_path),
                    "title": note.title,
                    "content": note.content,
                    "frontmatter": note.frontmatter,
                })
            except ValueError as exc:
                return _error(str(exc), date=date)

        @self.server.tool()
        async def obsidian_append_daily(
            content: str,
            date: str | None = None,
        ) -> list[TextContent]:
            """Append content to a daily note.

            Args:
                content: Content to append
                date: Date in YYYY-MM-DD format (defaults to today)
            """
            self._ensure_setup()
            try:
                from datetime import datetime as dt
                target = dt.strptime(date, "%Y-%m-%d") if date else None
                note = self.daily.append_to_daily(content, date=target)
                return _json_text({"status": "appended", "path": str(note.file_path)})
            except ValueError as exc:
                return _error(str(exc), date=date)

        # ----------------------------------------------------------
        # Memory / Knowledge store
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_save_memory(
            content: str,
            title: str = "",
            category: str = "general",
            tags: str = "[]",
            importance: int = 3,
            agent: str = "agent",
            related_notes: str = "[]",
            related_memories: str = "[]",
        ) -> list[TextContent]:
            """Save a memory to the unified knowledge store.

            All agents share this memory pool. Duplicates are auto-detected
            and merged. Each memory tracks which agent created it.

            Args:
                content: The memory content to save
                title: Title (auto-generated from content if empty)
                category: fact/task/insight/conversation/preference/rule/general
                tags: JSON array of additional tags (e.g. '["python", "tips"]')
                importance: 1 (low) to 5 (critical)
                agent: Which agent is saving (codex/claude/cursor/user)
                related_notes: JSON array of related vault note names
                related_memories: JSON array of related memory IDs (mem-xxx)
            """
            self._ensure_setup()
            try:
                tag_list = _parse_json(tags, "tags") if tags not in ("", "[]") else None
                related = _parse_json(related_notes, "related_notes") if related_notes not in ("", "[]") else None
                related_mems = _parse_json(related_memories, "related_memories") if related_memories not in ("", "[]") else None
                result = self.memory.save_memory(
                    content=content,
                    title=title,
                    category=category,
                    tags=tag_list,
                    importance=importance,
                    agent=agent,
                    related_notes=related,
                    related_memories=related_mems,
                )
                return _json_text(result)
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_recall_memories(
            query: str | None = None,
            category: str | None = None,
            agent: str | None = None,
            min_importance: int = 1,
            include_archived: bool = False,
            limit: int = 10,
        ) -> list[TextContent]:
            """Search and retrieve memories from the unified knowledge store.

            All agents share this memory pool.

            Args:
                query: Text to search for (omit to list recent memories)
                category: Filter by category (fact/task/insight/conversation/preference/rule)
                agent: Filter by creator agent (codex/claude/cursor/user)
                min_importance: Minimum importance level (1-5)
                include_archived: Include archived memories in results
                limit: Maximum results
            """
            self._ensure_setup()
            try:
                results = self.memory.recall_memories(
                    query=query,
                    category=category,
                    agent=agent,
                    min_importance=min_importance,
                    include_archived=include_archived,
                    limit=limit,
                )
                return _json_text({"count": len(results), "memories": results})
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_forget_memory(path: str) -> list[TextContent]:
            """Delete a stored memory by path or memory ID.

            Args:
                path: Vault-relative path of the memory note, or a memory ID (mem-xxx)
            """
            self._ensure_setup()
            try:
                deleted = self.memory.forget_memory(path)
                if deleted:
                    return _json_text({"status": "forgotten", "path": path})
                return _error("Memory not found", path=path)
            except (FileNotFoundError, ValueError) as exc:
                return _error(str(exc), path=path)

        @self.server.tool()
        async def obsidian_memory_merge(
            memory_ids: str,
            merged_content: str,
            title: str = "",
            agent: str = "agent",
            importance: int = 4,
        ) -> list[TextContent]:
            """Merge multiple memories into one consolidated memory.

            Original memories are archived and a new merged memory is created
            with references to the originals.

            Args:
                memory_ids: JSON array of memory IDs to merge (e.g. '["mem-xxx", "mem-yyy"]')
                merged_content: The consolidated content
                title: Title for the merged memory
                agent: Which agent is performing the merge
                importance: Importance level for the merged memory (1-5)
            """
            self._ensure_setup()
            try:
                ids = _parse_json(memory_ids, "memory_ids")
                result = self.memory.merge_memories(
                    ids, merged_content, title=title, agent=agent, importance=importance
                )
                return _json_text(result)
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_memory_access(memory_id: str) -> list[TextContent]:
            """Mark a memory as accessed (bumps access count and updates last_accessed).

            Args:
                memory_id: The memory ID (mem-xxx) to mark as accessed
            """
            self._ensure_setup()
            try:
                result = self.memory.access_memory(memory_id)
                if result:
                    return _json_text(result)
                return _error("Memory not found", memory_id=memory_id)
            except ValueError as exc:
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_memory_lifecycle() -> list[TextContent]:
            """Run memory lifecycle maintenance.

            Decays importance of unused memories and archives old low-importance ones.
            Should be called periodically to keep the memory store healthy.
            """
            self._ensure_setup()
            try:
                result = self.memory.run_lifecycle()
                return _json_text(result)
            except Exception as exc:
                logger.exception("Lifecycle error")
                return _error(str(exc))

        @self.server.tool()
        async def obsidian_memory_stats() -> list[TextContent]:
            """Get memory store statistics (counts by agent, category, importance)."""
            self._ensure_setup()
            try:
                stats = self.memory.get_stats()
                return _json_text(stats)
            except Exception as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # Vault stats
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_vault_stats() -> list[TextContent]:
            """Get statistics about the Obsidian vault (note count, size, etc.)."""
            self._ensure_setup()
            try:
                stats = self.vault.get_stats()
                return _json_text(stats)
            except Exception as exc:
                return _error(str(exc))

        # ----------------------------------------------------------
        # REST API tools (only registered when REST API is enabled)
        # ----------------------------------------------------------

        if self.config and self.config.rest_api_enabled:

            @self.server.tool()
            async def obsidian_rest_search(
                query: str,
                context_length: int = 100,
            ) -> list[TextContent]:
                """Search notes via the Obsidian Local REST API plugin.

                Uses Obsidian's built-in search engine. Requires the
                'Local REST API' community plugin to be installed and running.

                Args:
                    query: Search query
                    context_length: Characters of context around matches
                """
                self._ensure_setup()
                try:
                    results = await self.rest_api.search(query, context_length)
                    return _json_text({"query": query, "results": results})
                except Exception as exc:
                    return _error(str(exc))

            @self.server.tool()
            async def obsidian_open_in_app(path: str) -> list[TextContent]:
                """Open a note in the Obsidian application.

                Requires the Local REST API plugin.

                Args:
                    path: Vault-relative path to the note
                """
                self._ensure_setup()
                try:
                    result = await self.rest_api.open_note(path)
                    return _json_text(result)
                except Exception as exc:
                    return _error(str(exc))

            @self.server.tool()
            async def obsidian_rest_api_status() -> list[TextContent]:
                """Check if the Obsidian Local REST API is available."""
                self._ensure_setup()
                try:
                    available = await self.rest_api.is_available()
                    return _json_text({
                        "enabled": True,
                        "available": available,
                        "url": self.config.rest_api_url,
                    })
                except Exception as exc:
                    return _error(str(exc))

    # ==================================================================
    # Run
    # ==================================================================

    async def run(self) -> None:
        """Start the MCP server over stdio."""
        # Eagerly initialise so REST tools are registered before the loop starts
        try:
            self._ensure_setup()
        except Exception:
            logger.warning("Could not initialise at startup; will retry on first tool call.")
        self.register_tools()
        await self.server.run_stdio_async()


def main() -> None:
    """Entry point for the obsidian-mcp command."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    server = ObsidianMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
