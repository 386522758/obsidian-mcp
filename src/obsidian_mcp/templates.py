"""Template management for Obsidian notes."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .vault import Vault


class TemplateManager:
    """Manage and apply Obsidian templates."""

    def __init__(self, config: ObsidianConfig, vault: Vault) -> None:
        self.config = config
        self.vault = vault
        self.templates_folder = config.templates_folder

    def _get_template_path(self, name: str) -> Path:
        """Get the full path to a template file."""
        if self.templates_folder:
            return self.config.resolve_path(f"{self.templates_folder}/{name}.md")
        # Search common locations
        for folder in ["templates", "Templates", ".templates"]:
            path = self.config.resolve_path(f"{folder}/{name}.md")
            if path.exists():
                return path
        # Try root
        return self.config.resolve_path(f"{name}.md")

    def list_templates(self) -> list[dict[str, str]]:
        """List available templates."""
        templates = []
        search_folders = [self.templates_folder] if self.templates_folder else [
            "templates", "Templates", ".templates"
        ]
        for folder in search_folders:
            try:
                base = self.config.resolve_path(folder)
                if not base.is_dir():
                    continue
                for md in sorted(base.glob("*.md")):
                    templates.append({
                        "name": md.stem,
                        "path": str(md.relative_to(self.config.vault_path)),
                        "folder": folder,
                    })
            except (ValueError, FileNotFoundError):
                continue
        return templates

    def get_template(self, name: str) -> str:
        """Read a template's content."""
        path = self._get_template_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {name}")
        return path.read_text(encoding="utf-8")

    def apply_template(
        self,
        template_name: str,
        variables: dict[str, str] | None = None,
        date: datetime | None = None,
    ) -> str:
        """Apply a template with variable substitution.
        
        Supports:
            {{date}} - Current date (or provided date)
            {{date:FORMAT}} - Custom date format
            {{title}} - From variables
            {{variable}} - Any custom variable
        """
        content = self.get_template(template_name)
        now = date or datetime.now()

        # Built-in variables
        builtins = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "datetime": now.strftime("%Y-%m-%d %H:%M"),
            "year": now.strftime("%Y"),
            "month": now.strftime("%m"),
            "day": now.strftime("%d"),
            "weekday": now.strftime("%A"),
        }

        if variables:
            builtins.update(variables)

        # Replace {{date:FORMAT}} patterns
        def replace_date_format(match: re.Match) -> str:
            fmt = match.group(1)
            return now.strftime(fmt)

        content = re.sub(r"\{\{date:([^}]+)\}\}", replace_date_format, content)

        # Replace {{variable}} patterns
        def replace_var(match: re.Match) -> str:
            key = match.group(1).strip()
            return builtins.get(key, match.group(0))

        content = re.sub(r"\{\{([^}]+)\}\}", replace_var, content)

        return content

    def create_from_template(
        self,
        template_name: str,
        note_path: str,
        variables: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new note from a template."""
        content = self.apply_template(template_name, variables)
        note = self.vault.create_note(note_path, content=content, overwrite=overwrite)
        return {
            "path": note_path,
            "template": template_name,
            "title": note.title,
        }
