"""Tests for Vault CRUD operations and path safety."""

import pytest
from pathlib import Path

from obsidian_mcp.config import ObsidianConfig
from obsidian_mcp.vault import Vault
from tests.conftest import write_note


# ---------------------------------------------------------------------------
# read_note
# ---------------------------------------------------------------------------

class TestReadNote:
    def test_reads_existing_note(self, vault, vault_path):
        write_note(vault_path, "note.md", "---\ntitle: Hi\n---\nHello")
        note = vault.read_note("note.md")
        assert note.frontmatter["title"] == "Hi"
        assert "Hello" in note.body

    def test_auto_appends_md_extension(self, vault, vault_path):
        write_note(vault_path, "note.md", "content")
        note = vault.read_note("note")
        assert note.body == "content"

    def test_raises_for_missing_note(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.read_note("does_not_exist.md")

    def test_nested_path(self, vault, vault_path):
        write_note(vault_path, "folder/sub/deep.md", "deep content")
        note = vault.read_note("folder/sub/deep.md")
        assert note.body == "deep content"


# ---------------------------------------------------------------------------
# read_raw
# ---------------------------------------------------------------------------

class TestReadRaw:
    def test_returns_raw_string(self, vault, vault_path):
        write_note(vault_path, "raw.md", "raw content here")
        assert vault.read_raw("raw.md") == "raw content here"

    def test_raises_for_missing(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.read_raw("missing.md")


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------

class TestListNotes:
    def test_lists_markdown_files(self, vault, vault_path):
        write_note(vault_path, "a.md", "")
        write_note(vault_path, "b.md", "")
        notes = vault.list_notes()
        paths = [n["path"] for n in notes]
        assert "a.md" in paths
        assert "b.md" in paths

    def test_excludes_hidden_directories(self, vault, vault_path):
        write_note(vault_path, ".obsidian/config.md", "")
        write_note(vault_path, "visible.md", "")
        notes = vault.list_notes()
        paths = [n["path"] for n in notes]
        assert "visible.md" in paths
        assert not any(".obsidian" in p for p in paths)

    def test_include_hidden_flag(self, vault, vault_path):
        write_note(vault_path, ".obsidian/config.md", "")
        notes = vault.list_notes(include_hidden=True)
        paths = [n["path"] for n in notes]
        assert any(".obsidian" in p for p in paths)

    def test_folder_filter(self, vault, vault_path):
        write_note(vault_path, "folder/in.md", "")
        write_note(vault_path, "out.md", "")
        notes = vault.list_notes(folder="folder")
        paths = [n["path"] for n in notes]
        assert any("in.md" in p for p in paths)
        assert not any("out.md" in p for p in paths)

    def test_nonrecursive(self, vault, vault_path):
        write_note(vault_path, "top.md", "")
        write_note(vault_path, "sub/deep.md", "")
        notes = vault.list_notes(recursive=False)
        paths = [n["path"] for n in notes]
        assert "top.md" in paths
        assert not any("deep.md" in p for p in paths)

    def test_raises_for_missing_folder(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.list_notes(folder="no_such_folder")


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------

class TestCreateNote:
    def test_creates_simple_note(self, vault, vault_path):
        note = vault.create_note("new.md", content="hello")
        assert (vault_path / "new.md").exists()
        assert note.body == "hello"

    def test_creates_with_frontmatter(self, vault, vault_path):
        note = vault.create_note("fm.md", content="body", frontmatter={"title": "FM"})
        assert note.frontmatter["title"] == "FM"
        assert "body" in note.body

    def test_creates_parent_dirs(self, vault, vault_path):
        vault.create_note("deep/dir/note.md", content="x")
        assert (vault_path / "deep" / "dir" / "note.md").exists()

    def test_raises_if_exists_without_overwrite(self, vault, vault_path):
        write_note(vault_path, "existing.md", "original")
        with pytest.raises(FileExistsError):
            vault.create_note("existing.md", content="new")

    def test_overwrites_with_flag(self, vault, vault_path):
        write_note(vault_path, "existing.md", "original")
        note = vault.create_note("existing.md", content="replaced", overwrite=True)
        assert note.body == "replaced"

    def test_auto_adds_md_extension(self, vault, vault_path):
        vault.create_note("no_ext", content="text")
        assert (vault_path / "no_ext.md").exists()


# ---------------------------------------------------------------------------
# update_note – four update modes
# ---------------------------------------------------------------------------

class TestUpdateNote:
    def _make(self, vault, vault_path, name="note.md", content="---\ntitle: Old\n---\nOriginal body"):
        write_note(vault_path, name, content)
        return name

    def test_replace_body_only(self, vault, vault_path):
        self._make(vault, vault_path)
        note = vault.update_note("note.md", content="New body")
        assert "New body" in note.body
        assert note.frontmatter["title"] == "Old"

    def test_append_body(self, vault, vault_path):
        self._make(vault, vault_path)
        vault.update_note("note.md", content="Appended", append=True)
        raw = vault.read_raw("note.md")
        assert "Original body" in raw
        assert "Appended" in raw

    def test_update_frontmatter_only(self, vault, vault_path):
        self._make(vault, vault_path)
        note = vault.update_note("note.md", frontmatter_updates={"status": "done"})
        assert note.frontmatter["status"] == "done"
        assert note.frontmatter["title"] == "Old"
        assert "Original body" in note.body

    def test_update_both_frontmatter_and_body(self, vault, vault_path):
        self._make(vault, vault_path)
        note = vault.update_note(
            "note.md",
            content="Replacement",
            frontmatter_updates={"status": "done"},
        )
        assert note.frontmatter["status"] == "done"
        assert note.frontmatter["title"] == "Old"
        assert "Replacement" in note.body

    def test_update_both_append_mode(self, vault, vault_path):
        self._make(vault, vault_path)
        vault.update_note(
            "note.md",
            content="Extra",
            frontmatter_updates={"count": 1},
            append=True,
        )
        raw = vault.read_raw("note.md")
        assert "Original body" in raw
        assert "Extra" in raw

    def test_no_changes_preserves_content(self, vault, vault_path):
        self._make(vault, vault_path)
        note = vault.update_note("note.md")
        assert note.frontmatter["title"] == "Old"
        assert "Original body" in note.body

    def test_raises_for_missing_note(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.update_note("ghost.md", content="x")

    def test_replace_body_on_note_without_frontmatter(self, vault, vault_path):
        write_note(vault_path, "plain.md", "Old plain body")
        note = vault.update_note("plain.md", content="New plain body")
        assert note.body == "New plain body"
        assert not note.has_frontmatter


# ---------------------------------------------------------------------------
# delete_note / move_note
# ---------------------------------------------------------------------------

class TestDeleteNote:
    def test_deletes_note(self, vault, vault_path):
        write_note(vault_path, "delete_me.md", "bye")
        vault.delete_note("delete_me.md")
        assert not (vault_path / "delete_me.md").exists()

    def test_raises_for_missing(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.delete_note("ghost.md")


class TestMoveNote:
    def test_moves_note(self, vault, vault_path):
        write_note(vault_path, "src.md", "content")
        new_path = vault.move_note("src.md", "dst.md")
        assert (vault_path / "dst.md").exists()
        assert not (vault_path / "src.md").exists()

    def test_move_creates_parent_dirs(self, vault, vault_path):
        write_note(vault_path, "src.md", "x")
        vault.move_note("src.md", "deep/folder/dst.md")
        assert (vault_path / "deep" / "folder" / "dst.md").exists()

    def test_raises_if_destination_exists(self, vault, vault_path):
        write_note(vault_path, "src.md", "a")
        write_note(vault_path, "dst.md", "b")
        with pytest.raises(FileExistsError):
            vault.move_note("src.md", "dst.md")

    def test_raises_if_source_missing(self, vault):
        with pytest.raises(FileNotFoundError):
            vault.move_note("ghost.md", "dst.md")


# ---------------------------------------------------------------------------
# get_backlinks / get_graph
# ---------------------------------------------------------------------------

class TestGetBacklinks:
    def test_finds_backlink(self, vault, vault_path):
        write_note(vault_path, "source.md", "See [[target]]")
        write_note(vault_path, "target.md", "I am the target")
        backlinks = vault.get_backlinks("target")
        assert any(b["name"] == "source" for b in backlinks)

    def test_no_backlinks(self, vault, vault_path):
        write_note(vault_path, "lone.md", "no links")
        assert vault.get_backlinks("lone") == []


class TestGetGraph:
    def test_builds_graph(self, vault, vault_path):
        write_note(vault_path, "a.md", "[[b]]")
        write_note(vault_path, "b.md", "[[c]]")
        write_note(vault_path, "c.md", "no links")
        graph = vault.get_graph()
        assert "b" in graph["a"]
        assert "c" in graph["b"]
        assert graph["c"] == []


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_counts_notes_and_folders(self, vault, vault_path):
        write_note(vault_path, "a.md", "")
        write_note(vault_path, "folder/b.md", "")
        stats = vault.get_stats()
        assert stats["total_notes"] == 2
        assert stats["total_folders"] == 1
