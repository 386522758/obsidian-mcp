"""Tests for ObsidianConfig – path resolution and environment loading."""

import os
import pytest
from pathlib import Path
from obsidian_mcp.config import ObsidianConfig


# ---------------------------------------------------------------------------
# resolve_path – security & correctness
# ---------------------------------------------------------------------------

class TestResolvePath:
    def test_simple_relative_path(self, config: ObsidianConfig, vault_path: Path):
        result = config.resolve_path("notes/foo.md")
        assert result == (vault_path / "notes" / "foo.md").resolve()

    def test_root_level_file(self, config: ObsidianConfig, vault_path: Path):
        result = config.resolve_path("README.md")
        assert result == (vault_path / "README.md").resolve()

    def test_traversal_two_dots(self, config: ObsidianConfig):
        with pytest.raises(ValueError, match="Path traversal"):
            config.resolve_path("../../etc/passwd")

    def test_traversal_after_valid_prefix(self, config: ObsidianConfig):
        """../.. starting inside the vault must still be caught."""
        with pytest.raises(ValueError, match="Path traversal"):
            config.resolve_path("notes/../../etc/shadow")

    def test_sibling_directory_not_allowed(self, tmp_path: Path):
        """A directory that shares the vault prefix string must be blocked.

        e.g. vault=/tmp/abc, target=/tmp/abc-sibling must not pass
        the startswith check.
        """
        vault = tmp_path / "vault"
        sibling = tmp_path / "vault-sibling"
        vault.mkdir()
        sibling.mkdir()
        cfg = ObsidianConfig(vault_path=vault)
        with pytest.raises(ValueError, match="Path traversal"):
            cfg.resolve_path("../vault-sibling/secret.md")

    def test_dot_path_is_vault_root(self, config: ObsidianConfig, vault_path: Path):
        result = config.resolve_path(".")
        assert result == vault_path.resolve()


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_raises_without_vault_path(self, monkeypatch):
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        with pytest.raises(ValueError, match="Vault path is required"):
            ObsidianConfig.from_env()

    def test_raises_when_path_does_not_exist(self, monkeypatch, tmp_path: Path):
        missing = str(tmp_path / "does_not_exist")
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", missing)
        with pytest.raises(ValueError, match="does not exist"):
            ObsidianConfig.from_env()

    def test_reads_vault_path_from_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        cfg = ObsidianConfig.from_env()
        assert cfg.vault_path == tmp_path

    def test_explicit_vault_path_overrides_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", "/nonexistent")
        cfg = ObsidianConfig.from_env(vault_path=str(tmp_path))
        assert cfg.vault_path == tmp_path

    def test_rest_api_enabled_true_variants(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        for truthy in ("true", "True", "1", "yes"):
            monkeypatch.setenv("OBSIDIAN_REST_API_ENABLED", truthy)
            cfg = ObsidianConfig.from_env()
            assert cfg.rest_api_enabled is True

    def test_rest_api_enabled_false_by_default(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        monkeypatch.delenv("OBSIDIAN_REST_API_ENABLED", raising=False)
        cfg = ObsidianConfig.from_env()
        assert cfg.rest_api_enabled is False

    def test_custom_memory_folder(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
        monkeypatch.setenv("OBSIDIAN_MEMORY_FOLDER", "brain")
        cfg = ObsidianConfig.from_env()
        assert cfg.memory_folder == "brain"


# ---------------------------------------------------------------------------
# _load_obsidian_settings
# ---------------------------------------------------------------------------

class TestLoadObsidianSettings:
    def test_loads_daily_notes_folder(self, vault_path: Path, config: ObsidianConfig):
        obsidian_dir = vault_path / ".obsidian"
        obsidian_dir.mkdir()
        (obsidian_dir / "app.json").write_text(
            '{"dailyNotesFolder": "Journal"}', encoding="utf-8"
        )
        config._load_obsidian_settings()
        assert config.daily_notes_folder == "Journal"

    def test_silently_ignores_malformed_json(self, vault_path: Path, config: ObsidianConfig):
        obsidian_dir = vault_path / ".obsidian"
        obsidian_dir.mkdir()
        (obsidian_dir / "app.json").write_text("not json {{", encoding="utf-8")
        config._load_obsidian_settings()  # must not raise

    def test_silently_ignores_missing_file(self, config: ObsidianConfig):
        config._load_obsidian_settings()  # must not raise
