"""Shared fixtures for obsidian-mcp tests."""

import pytest
from pathlib import Path
from obsidian_mcp.config import ObsidianConfig
from obsidian_mcp.vault import Vault


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    """An empty temporary directory representing an Obsidian vault root."""
    return tmp_path


@pytest.fixture
def config(vault_path: Path) -> ObsidianConfig:
    """ObsidianConfig pointing at the temporary vault."""
    return ObsidianConfig(vault_path=vault_path)


@pytest.fixture
def vault(config: ObsidianConfig) -> Vault:
    """Vault instance backed by the temporary vault."""
    return Vault(config)


def write_note(vault_path: Path, rel_path: str, content: str) -> Path:
    """Helper: write a markdown file directly into the vault."""
    p = vault_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p
