"""Daily notes management for Obsidian."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .parser import ParsedNote
from .vault import Vault


class DailyNotesManager:
    """Manage Obsidian daily notes."""

    def __init__(self, config: ObsidianConfig, vault: Vault) -> None:
        self.config = config
        self.vault = vault

    def _daily_path(self, date: datetime) -> str:
        """Get the vault-relative path for a daily note."""
        filename = date.strftime(self.config.daily_notes_format)
        if self.config.daily_notes_folder:
            return f"{self.config.daily_notes_folder}/{filename}.md"
        return f"{filename}.md"

    def get_today(self) -> ParsedNote:
        """Get today's daily note (create if it doesn't exist)."""
        return self.get_daily(datetime.now())

    def get_daily(self, date: datetime) -> ParsedNote:
        """Get a daily note for a specific date."""
        path = self._daily_path(date)
        try:
            return self.vault.read_note(path)
        except FileNotFoundError:
            # Create from template if available
            content = self._generate_daily_content(date)
            return self.vault.create_note(
                path,
                content=content,
                frontmatter={
                    "date": date.strftime("%Y-%m-%d"),
                    "tags": ["daily"],
                },
            )

    def append_to_daily(
        self, content: str, date: datetime | None = None
    ) -> ParsedNote:
        """Append content to today's (or specified date's) daily note."""
        target_date = date or datetime.now()
        path = self._daily_path(target_date)
        try:
            return self.vault.update_note(path, content=content, append=True)
        except FileNotFoundError:
            # Create and append
            note = self.get_daily(target_date)
            return self.vault.update_note(path, content=content, append=True)

    def list_daily_notes(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict[str, Any]]:
        """List daily notes in a date range."""
        folder = self.config.daily_notes_folder
        notes = self.vault.list_notes(folder=folder, recursive=False)
        # Filter by date range if provided
        if start or end:
            filtered = []
            for note in notes:
                name = Path(note["name"]).stem
                try:
                    note_date = datetime.strptime(name, self.config.daily_notes_format)
                except ValueError:
                    continue
                if start and note_date < start:
                    continue
                if end and note_date > end:
                    continue
                filtered.append(note)
            return filtered
        return notes

    def _generate_daily_content(self, date: datetime) -> str:
        """Generate default content for a new daily note."""
        weekday = date.strftime("%A")
        return f"""# {date.strftime('%Y-%m-%d')} ({weekday})

## Tasks

- [ ] 

## Notes



## Journal


"""
