"""Core vault file operations - read, write, create, delete, list notes."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .parser import ParsedNote, parse_note, build_frontmatter, update_frontmatter


class Vault:
    """Direct file-system access to an Obsidian vault."""

    def __init__(self, config: ObsidianConfig) -> None:
        self.config = config
        self.root = config.vault_path.resolve()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _safe_path(self, relative: str) -> Path:
        """Resolve and validate a vault-relative path."""
        return self.config.resolve_path(relative)

    def _relative(self, path: Path) -> str:
        """Return vault-relative string for *path*."""
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def _ensure_md(self, path: Path) -> Path:
        """Append .md extension if missing."""
        if path.suffix != ".md":
            return path.with_suffix(path.suffix + ".md")
        return path

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def read_note(self, relative_path: str) -> ParsedNote:
        """Read and parse a single note by vault-relative path."""
        path = self._ensure_md(self._safe_path(relative_path))
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        content = path.read_text(encoding="utf-8")
        stat = path.stat()
        return parse_note(content, file_path=path, file_stat=stat)

    def read_raw(self, relative_path: str) -> str:
        """Read raw content of a note (no parsing)."""
        path = self._safe_path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return path.read_text(encoding="utf-8")

    def list_notes(
        self,
        folder: str = "",
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        """List all markdown notes, optionally filtered by folder.
        
        Returns list of dicts with path, name, folder, size, modified fields.
        """
        base = self._safe_path(folder) if folder else self.root
        if not base.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder}")

        pattern = "**/*.md" if recursive else "*.md"
        notes = []
        for md_file in sorted(base.glob(pattern)):
            # Skip hidden directories
            rel = md_file.relative_to(self.root)
            parts = rel.parts
            if not include_hidden and any(p.startswith(".") for p in parts):
                continue

            stat = md_file.stat()
            notes.append({
                "path": self._relative(md_file),
                "name": md_file.stem,
                "folder": str(rel.parent) if str(rel.parent) != "." else "",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return notes

    def list_folders(self, folder: str = "") -> list[str]:
        """List subdirectories in a folder."""
        base = self._safe_path(folder) if folder else self.root
        if not base.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder}")
        return [
            self._relative(d)
            for d in sorted(base.iterdir())
            if d.is_dir() and not d.name.startswith(".")
        ]

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_note(
        self,
        relative_path: str,
        content: str = "",
        frontmatter: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> ParsedNote:
        """Create a new note.
        
        Args:
            relative_path: Vault-relative path (with or without .md)
            content: Body content
            frontmatter: Optional YAML frontmatter dict
            overwrite: Whether to overwrite existing notes
        """
        path = self._ensure_md(self._safe_path(relative_path))
        if path.exists() and not overwrite:
            raise FileExistsError(f"Note already exists: {relative_path}")

        path.parent.mkdir(parents=True, exist_ok=True)

        full_content = ""
        if frontmatter:
            full_content = build_frontmatter(frontmatter)
        full_content += content

        path.write_text(full_content, encoding="utf-8")
        return parse_note(full_content, file_path=path, file_stat=path.stat())

    def update_note(
        self,
        relative_path: str,
        content: str | None = None,
        frontmatter_updates: dict[str, Any] | None = None,
        append: bool = False,
    ) -> ParsedNote:
        """Update an existing note.
        
        Args:
            relative_path: Vault-relative path
            content: New body content (replaces existing if not append)
            frontmatter_updates: Frontmatter fields to update/merge
            append: If True, append content to end instead of replacing
        """
        path = self._ensure_md(self._safe_path(relative_path))
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")

        existing = path.read_text(encoding="utf-8")

        if frontmatter_updates and content is not None:
            # Update both
            new_content = update_frontmatter(existing, frontmatter_updates)
            if append:
                new_content = new_content.rstrip("\n") + "\n\n" + content
            else:
                # Replace body but keep frontmatter
                _, _ = __import__("obsidian_mcp.parser", fromlist=["parse_frontmatter"]).parse_frontmatter(new_content)
                new_content = update_frontmatter(existing, frontmatter_updates)
                # Re-build with new body
                fm_str = new_content.split("---\n", 2)[1] if new_content.startswith("---") else ""
                if fm_str:
                    fm_end = fm_str.index("---\n")
                    new_content = f"---\n{fm_str[:fm_end]}---\n\n{content}"
        elif frontmatter_updates:
            new_content = update_frontmatter(existing, frontmatter_updates)
        elif content is not None:
            if append:
                new_content = existing.rstrip("\n") + "\n\n" + content
            else:
                # Keep frontmatter, replace body
                from .parser import parse_frontmatter
                fm, _ = parse_frontmatter(existing)
                if fm:
                    new_content = build_frontmatter(fm) + content
                else:
                    new_content = content
        else:
            new_content = existing

        path.write_text(new_content, encoding="utf-8")
        return parse_note(new_content, file_path=path, file_stat=path.stat())

    def delete_note(self, relative_path: str) -> bool:
        """Delete a note. Returns True if deleted."""
        path = self._ensure_md(self._safe_path(relative_path))
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        path.unlink()
        return True

    def move_note(self, source: str, destination: str) -> str:
        """Move/rename a note. Returns new relative path."""
        src = self._ensure_md(self._safe_path(source))
        dst = self._ensure_md(self._safe_path(destination))
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        if dst.exists():
            raise FileExistsError(f"Destination exists: {destination}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return self._relative(dst)

    # ------------------------------------------------------------------
    # Advanced operations
    # ------------------------------------------------------------------

    def get_backlinks(self, note_name: str) -> list[dict[str, str]]:
        """Find all notes that link to the given note name."""
        from .parser import WIKILINK_RE
        backlinks = []
        for md_file in self.root.rglob("*.md"):
            rel = md_file.relative_to(self.root)
            if any(p.startswith(".") for p in rel.parts):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in WIKILINK_RE.finditer(content):
                target = match.group(1).strip().split("|")[0].strip()
                if target == note_name or target == note_name.replace(".md", ""):
                    backlinks.append({
                        "path": self._relative(md_file),
                        "name": md_file.stem,
                        "context": content[
                            max(0, match.start() - 50):match.end() + 50
                        ].replace("\n", " "),
                    })
                    break
        return backlinks

    def get_graph(self, depth: int = 1) -> dict[str, list[str]]:
        """Build a simplified link graph of the vault."""
        from .parser import WIKILINK_RE
        graph: dict[str, list[str]] = {}
        for md_file in self.root.rglob("*.md"):
            rel = md_file.relative_to(self.root)
            if any(p.startswith(".") for p in rel.parts):
                continue
            name = md_file.stem
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            links = [
                m.group(1).strip().split("|")[0].strip()
                for m in WIKILINK_RE.finditer(content)
            ]
            graph[name] = links
        return graph

    def get_stats(self) -> dict[str, Any]:
        """Get vault statistics."""
        notes = list(self.root.rglob("*.md"))
        total_size = sum(n.stat().st_size for n in notes)
        folders = set()
        for n in notes:
            rel = n.relative_to(self.root)
            if len(rel.parts) > 1:
                folders.add(str(rel.parent))
        return {
            "total_notes": len(notes),
            "total_folders": len(folders),
            "total_size_bytes": total_size,
            "vault_path": str(self.root),
        }
