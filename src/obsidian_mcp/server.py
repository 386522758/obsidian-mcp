#!/usr/bin/env python3
"""Obsidian MCP Server.

Exposes Obsidian vault operations as MCP tools for AI agents.
Supports both direct file access and the Obsidian Local REST API plugin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import (
    TextContent,
    Tool,
)

from .config import ObsidianConfig
from .daily import DailyNotesManager
from .memory import MemoryStore
from .parser import parse_note, build_frontmatter, update_frontmatter, make_wikilink
from .rest_api import ObsidianRestAPI
from .search import SearchEngine
from .templates import TemplateManager
from .vault import Vault

logger = logging.getLogger("obsidian-mcp")


def _text(content: str) -> list[TextContent]:
    """Helper to wrap text in MCP TextContent."""
    return [TextContent(type="text", text=content)]


def _json_text(data: Any) -> list[TextContent]:
    """Helper to serialize data as JSON TextContent."""
    return _text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


class ObsidianMCPServer:
    """MCP Server exposing Obsidian vault tools."""

    def __init__(self) -> None:
        self.server = Server("obsidian-mcp")
        self.config: ObsidianConfig | None = None
        self.vault: Vault | None = None
        self.search: SearchEngine | None = None
        self.rest_api: ObsidianRestAPI | None = None
        self.templates: TemplateManager | None = None
        self.daily: DailyNotesManager | None = None
        self.memory: MemoryStore | None = None
        self._setup_done = False

    def _ensure_setup(self) -> None:
        """Lazy initialization from environment."""
        if self._setup_done:
            return
        self.config = ObsidianConfig.from_env()
        self.vault = Vault(self.config)
        self.search = SearchEngine(self.config)
        self.templates = TemplateManager(self.config, self.vault)
        self.daily = DailyNotesManager(self.config, self.vault)
        self.memory = MemoryStore(self.config, self.vault)
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
                path: Vault-relative path to the note (e.g. "20.areas/Python基础语法总结.md")
            """
            self._ensure_setup()
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
                frontmatter: JSON string of frontmatter metadata (e.g. '{"tags": ["python"], "status": "draft"}')
                overwrite: Whether to overwrite if a note already exists at this path
            """
            self._ensure_setup()
            fm = json.loads(frontmatter) if frontmatter and frontmatter != "{}" else None
            note = self.vault.create_note(path, content=content, frontmatter=fm, overwrite=overwrite)
            return _json_text({
                "status": "created",
                "path": path,
                "title": note.title,
            })

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
            fm_updates = json.loads(frontmatter) if frontmatter else None
            note = self.vault.update_note(
                path, content=content, frontmatter_updates=fm_updates, append=append
            )
            return _json_text({
                "status": "updated",
                "path": path,
                "title": note.title,
            })

        @self.server.tool()
        async def obsidian_delete_note(path: str) -> list[TextContent]:
            """Delete an Obsidian note.

            Args:
                path: Vault-relative path to the note to delete
            """
            self._ensure_setup()
            self.vault.delete_note(path)
            return _json_text({"status": "deleted", "path": path})

        @self.server.tool()
        async def obsidian_move_note(source: str, destination: str) -> list[TextContent]:
            """Move or rename an Obsidian note.

            Args:
                source: Current vault-relative path
                destination: New vault-relative path
            """
            self._ensure_setup()
            new_path = self.vault.move_note(source, destination)
            return _json_text({"status": "moved", "from": source, "to": new_path})

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
            notes = self.vault.list_notes(folder=folder, recursive=recursive)
            return _json_text({"count": len(notes), "notes": notes})

        @self.server.tool()
        async def obsidian_list_folders(folder: str = "") -> list[TextContent]:
            """List subdirectories in a vault folder.

            Args:
                folder: Parent folder (empty = vault root)
            """
            self._ensure_setup()
            folders = self.vault.list_folders(folder=folder)
            return _json_text({"folders": folders})

        @self.server.tool()
        async def obsidian_get_backlinks(note_name: str) -> list[TextContent]:
            """Find all notes that link to a given note via wikilinks.

            Args:
                note_name: The note name (without .md) to find backlinks for
            """
            self._ensure_setup()
            backlinks = self.vault.get_backlinks(note_name)
            return _json_text({"note": note_name, "backlinks": backlinks})

        @self.server.tool()
        async def obsidian_get_graph() -> list[TextContent]:
            """Get the vault's link graph showing wikilink relationships between all notes."""
            self._ensure_setup()
            graph = self.vault.get_graph()
            return _json_text({"nodes": len(graph), "graph": graph})

        # ----------------------------------------------------------
        # Search
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_search(
            query: str,
            folder: str = "",
            limit: int = 20,
        ) -> list[TextContent]:
            """Full-text search across all notes in the vault.

            Supports +term for must-have and -term for exclusion.

            Args:
                query: Search query (e.g. "python 函数" or "+machine -learning")
                folder: Limit search to a specific folder
                limit: Maximum number of results
            """
            self._ensure_setup()
            results = self.search.fulltext_search(query, folder=folder, limit=limit)
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

        @self.server.tool()
        async def obsidian_search_by_tag(tag: str, limit: int = 50) -> list[TextContent]:
            """Find all notes with a specific tag.

            Args:
                tag: Tag to search for (without #)
                limit: Maximum results
            """
            self._ensure_setup()
            results = self.search.tag_search(tag, limit=limit)
            return _json_text({
                "tag": tag,
                "count": len(results),
                "results": [
                    {"path": r.path, "name": r.name, "tags": r.tags}
                    for r in results
                ],
            })

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
            updates = json.loads(metadata)
            note = self.vault.update_note(path, frontmatter_updates=updates)
            return _json_text({
                "status": "updated",
                "path": path,
                "frontmatter": note.frontmatter,
            })

        # ----------------------------------------------------------
        # Templates
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_list_templates() -> list[TextContent]:
            """List available Obsidian templates."""
            self._ensure_setup()
            templates = self.templates.list_templates()
            return _json_text({"count": len(templates), "templates": templates})

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
                variables: JSON string of custom variables (e.g. '{"title": "My Note", "project": "Research"}')
            """
            self._ensure_setup()
            vars_dict = json.loads(variables) if variables and variables != "{}" else None
            result = self.templates.create_from_template(
                template, note_path, variables=vars_dict
            )
            return _json_text(result)

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
            if date:
                from datetime import datetime as dt
                target = dt.strptime(date, "%Y-%m-%d")
            else:
                target = None
            note = self.daily.get_daily(target) if target else self.daily.get_today()
            return _json_text({
                "path": str(note.file_path),
                "title": note.title,
                "content": note.content,
                "frontmatter": note.frontmatter,
            })

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
            from datetime import datetime as dt
            target = dt.strptime(date, "%Y-%m-%d") if date else None
            note = self.daily.append_to_daily(content, date=target)
            return _json_text({
                "status": "appended",
                "path": str(note.file_path),
            })

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
            source: str = "agent",
            related_notes: str = "[]",
        ) -> list[TextContent]:
            """Save a memory/knowledge item to Obsidian.

            Memories are stored as individual notes with metadata,
            enabling future recall and knowledge building.

            Args:
                content: The memory content to save
                title: Title (auto-generated from content if empty)
                category: Category (general, conversation, fact, task, insight, etc.)
                tags: JSON array of additional tags
                importance: 1 (low) to 5 (critical)
                source: Where this memory came from (agent, user, conversation, etc.)
                related_notes: JSON array of related note names for wikilinks
            """
            self._ensure_setup()
            tag_list = json.loads(tags) if tags and tags != "[]" else None
            related = json.loads(related_notes) if related_notes and related_notes != "[]" else None
            result = self.memory.save_memory(
                content=content,
                title=title,
                category=category,
                tags=tag_list,
                importance=importance,
                source=source,
                related_notes=related,
            )
            return _json_text(result)

        @self.server.tool()
        async def obsidian_recall_memories(
            query: str | None = None,
            category: str | None = None,
            min_importance: int = 1,
            limit: int = 10,
        ) -> list[TextContent]:
            """Search and retrieve stored memories from Obsidian.

            Args:
                query: Text to search for (omit to list recent memories)
                category: Filter by category
                min_importance: Minimum importance level (1-5)
                limit: Maximum results
            """
            self._ensure_setup()
            results = self.memory.recall_memories(
                query=query,
                category=category,
                min_importance=min_importance,
                limit=limit,
            )
            return _json_text({"count": len(results), "memories": results})

        @self.server.tool()
        async def obsidian_forget_memory(path: str) -> list[TextContent]:
            """Delete a stored memory.

            Args:
                path: Vault-relative path of the memory note to delete
            """
            self._ensure_setup()
            self.memory.forget_memory(path)
            return _json_text({"status": "forgotten", "path": path})

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
                display: Optional display text
            """
            link = make_wikilink(target, display)
            return _text(link)

        # ----------------------------------------------------------
        # Vault stats
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_vault_stats() -> list[TextContent]:
            """Get statistics about the Obsidian vault (note count, size, etc.)."""
            self._ensure_setup()
            stats = self.vault.get_stats()
            return _json_text(stats)

        # ----------------------------------------------------------
        # REST API tools (only when enabled)
        # ----------------------------------------------------------

        @self.server.tool()
        async def obsidian_rest_search(
            query: str,
            context_length: int = 100,
        ) -> list[TextContent]:
            """Search notes via the Obsidian Local REST API plugin.

            This uses Obsidian's built-in search engine and requires
            the 'Local REST API' community plugin to be installed and running.

            Args:
                query: Search query
                context_length: Characters of context around matches
            """
            self._ensure_setup()
            if not self.rest_api:
                return _text("REST API not enabled. Set OBSIDIAN_REST_API_ENABLED=true and install the Local REST API plugin.")
            results = self.rest_api.search(query, context_length)
            return _json_text({"query": query, "results": results})

        @self.server.tool()
        async def obsidian_open_in_app(path: str) -> list[TextContent]:
            """Open a note in the Obsidian application.

            Requires the Local REST API plugin.

            Args:
                path: Vault-relative path to the note
            """
            self._ensure_setup()
            if not self.rest_api:
                return _text("REST API not enabled. Set OBSIDIAN_REST_API_ENABLED=true and install the Local REST API plugin.")
            result = self.rest_api.open_note(path)
            return _json_text(result)

        @self.server.tool()
        async def obsidian_rest_api_status() -> list[TextContent]:
            """Check if the Obsidian Local REST API is available."""
            self._ensure_setup()
            if not self.rest_api:
                return _json_text({
                    "enabled": False,
                    "message": "REST API not configured. Set OBSIDIAN_REST_API_ENABLED=true.",
                })
            available = self.rest_api.is_available()
            return _json_text({
                "enabled": True,
                "available": available,
                "url": self.config.rest_api_url,
            })

    # ==================================================================
    # Resource registration (vault overview as a resource)
    # ==================================================================

    def register_resources(self) -> None:
        """Register MCP resources."""

        @self.server.resource("obsidian://vault")
        async def vault_overview() -> str:
            """Overview of the Obsidian vault."""
            self._ensure_setup()
            stats = self.vault.get_stats()
            notes = self.vault.list_notes()
            folders = self.vault.list_folders()
            return json.dumps({
                "stats": stats,
                "folders": folders,
                "recent_notes": notes[:20],
            }, ensure_ascii=False, indent=2)

    # ==================================================================
    # Run
    # ==================================================================

    async def run(self) -> None:
        """Start the MCP server over stdio."""
        self.register_tools()
        self.register_resources()
        await run_server(self.server)


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
