"""Configuration management for Obsidian MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ObsidianConfig:
    """Configuration for connecting to an Obsidian vault."""

    # Path to the Obsidian vault root
    vault_path: Path

    # Obsidian Local REST API settings
    rest_api_url: str = "https://localhost:27124"
    rest_api_token: str = ""
    rest_api_enabled: bool = False

    # Daily notes settings
    daily_notes_folder: str = ""
    daily_notes_format: str = "%Y-%m-%d"
    daily_notes_template: str = ""

    # Template settings
    templates_folder: str = ""

    # Memory settings
    memory_folder: str = "memories"

    @classmethod
    def from_env(cls, vault_path: str | None = None) -> ObsidianConfig:
        """Create config from environment variables.
        
        Environment variables:
            OBSIDIAN_VAULT_PATH: Path to the vault
            OBSIDIAN_REST_API_URL: REST API URL (default: https://localhost:27124)
            OBSIDIAN_REST_API_TOKEN: REST API auth token
            OBSIDIAN_REST_API_ENABLED: Enable REST API (true/false)
            OBSIDIAN_DAILY_NOTES_FOLDER: Daily notes subfolder
            OBSIDIAN_DAILY_NOTES_FORMAT: Date format for daily notes
            OBSIDIAN_TEMPLATES_FOLDER: Templates subfolder
            OBSIDIAN_MEMORY_FOLDER: Memory storage subfolder
        """
        vp = vault_path or os.environ.get("OBSIDIAN_VAULT_PATH", "")
        if not vp:
            raise ValueError(
                "Vault path is required. Set OBSIDIAN_VAULT_PATH env var "
                "or pass vault_path argument."
            )
        vault = Path(vp)
        if not vault.is_dir():
            raise ValueError(f"Vault path does not exist: {vault}")

        return cls(
            vault_path=vault,
            rest_api_url=os.environ.get(
                "OBSIDIAN_REST_API_URL", "https://localhost:27124"
            ),
            rest_api_token=os.environ.get("OBSIDIAN_REST_API_TOKEN", ""),
            rest_api_enabled=os.environ.get(
                "OBSIDIAN_REST_API_ENABLED", "false"
            ).lower() in ("true", "1", "yes"),
            daily_notes_folder=os.environ.get("OBSIDIAN_DAILY_NOTES_FOLDER", ""),
            daily_notes_format=os.environ.get(
                "OBSIDIAN_DAILY_NOTES_FORMAT", "%Y-%m-%d"
            ),
            templates_folder=os.environ.get("OBSIDIAN_TEMPLATES_FOLDER", ""),
            memory_folder=os.environ.get("OBSIDIAN_MEMORY_FOLDER", "memories"),
        )

    def _load_obsidian_settings(self) -> None:
        """Try to read settings from the vault's .obsidian config."""
        app_json = self.vault_path / ".obsidian" / "app.json"
        if app_json.exists():
            import json
            try:
                settings = json.loads(app_json.read_text(encoding="utf-8"))
                if "dailyNotesFolder" in settings:
                    self.daily_notes_folder = settings["dailyNotesFolder"]
                if "dailyNotesFormat" in settings:
                    self.daily_notes_format = settings["dailyNotesFormat"]
                if "newFileFolderPath" in settings:
                    pass  # could use as default folder
            except (json.JSONDecodeError, OSError):
                pass

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a path relative to the vault root, with safety checks."""
        target = (self.vault_path / relative_path).resolve()
        vault_resolved = self.vault_path.resolve()
        # Use relative_to() instead of startswith() so that a sibling directory
        # sharing a path prefix (e.g. /vault-sibling vs /vault) is correctly rejected.
        try:
            target.relative_to(vault_resolved)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {relative_path} escapes vault root"
            )
        return target
