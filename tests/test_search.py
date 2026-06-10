"""Tests for SearchEngine – fulltext, tag, metadata, and link search."""

import pytest
from pathlib import Path

from obsidian_mcp.config import ObsidianConfig
from obsidian_mcp.search import SearchEngine
from tests.conftest import write_note


@pytest.fixture
def engine(config: ObsidianConfig) -> SearchEngine:
    return SearchEngine(config)


# ---------------------------------------------------------------------------
# fulltext_search
# ---------------------------------------------------------------------------

class TestFulltextSearch:
    def test_finds_matching_note(self, engine, vault_path):
        write_note(vault_path, "a.md", "Python is great")
        results = engine.fulltext_search("python")
        assert any(r.name == "a" for r in results)

    def test_case_insensitive_by_default(self, engine, vault_path):
        write_note(vault_path, "a.md", "PYTHON rocks")
        results = engine.fulltext_search("python")
        assert len(results) == 1

    def test_case_sensitive_no_match(self, engine, vault_path):
        write_note(vault_path, "a.md", "PYTHON rocks")
        results = engine.fulltext_search("python", case_sensitive=True)
        assert len(results) == 0

    def test_case_sensitive_match(self, engine, vault_path):
        write_note(vault_path, "a.md", "PYTHON rocks")
        results = engine.fulltext_search("PYTHON", case_sensitive=True)
        assert len(results) == 1

    def test_exclusion_operator(self, engine, vault_path):
        write_note(vault_path, "keep.md", "python tips")
        write_note(vault_path, "drop.md", "python and java tips")
        results = engine.fulltext_search("python -java")
        names = [r.name for r in results]
        assert "keep" in names
        assert "drop" not in names

    def test_required_operator(self, engine, vault_path):
        write_note(vault_path, "match.md", "python django web")
        write_note(vault_path, "nomatch.md", "python only")
        results = engine.fulltext_search("python +django")
        names = [r.name for r in results]
        assert "match" in names
        assert "nomatch" not in names

    def test_mixed_boolean_operators(self, engine, vault_path):
        write_note(vault_path, "good.md", "python django tips")
        write_note(vault_path, "bad1.md", "python django rails")
        write_note(vault_path, "bad2.md", "python tips only")
        results = engine.fulltext_search("python +django -rails")
        names = [r.name for r in results]
        assert "good" in names
        assert "bad1" not in names
        assert "bad2" not in names

    def test_limit_respected(self, engine, vault_path):
        for i in range(10):
            write_note(vault_path, f"note{i}.md", "common word")
        results = engine.fulltext_search("common", limit=3)
        assert len(results) <= 3

    def test_folder_scoping(self, engine, vault_path):
        write_note(vault_path, "folder/inside.md", "keyword")
        write_note(vault_path, "outside.md", "keyword")
        results = engine.fulltext_search("keyword", folder="folder")
        names = [r.name for r in results]
        assert "inside" in names
        assert "outside" not in names

    def test_no_results_for_absent_term(self, engine, vault_path):
        write_note(vault_path, "a.md", "nothing relevant")
        assert engine.fulltext_search("zzzyyyxxx") == []

    def test_hidden_directories_excluded(self, engine, vault_path):
        write_note(vault_path, ".obsidian/hidden.md", "secret keyword")
        write_note(vault_path, "visible.md", "keyword")
        results = engine.fulltext_search("keyword")
        names = [r.name for r in results]
        assert "visible" in names
        assert "hidden" not in names

    def test_results_sorted_by_score_descending(self, engine, vault_path):
        write_note(vault_path, "low.md", "python once")
        write_note(vault_path, "high.md", "python python python")
        results = engine.fulltext_search("python")
        assert results[0].name == "high"

    def test_snippet_contains_match(self, engine, vault_path):
        write_note(vault_path, "note.md", "The quick brown fox")
        results = engine.fulltext_search("fox")
        assert "fox" in results[0].snippet.lower()


# ---------------------------------------------------------------------------
# tag_search
# ---------------------------------------------------------------------------

class TestTagSearch:
    def test_finds_inline_tag(self, engine, vault_path):
        write_note(vault_path, "tagged.md", "content #python")
        results = engine.tag_search("python")
        assert any(r.name == "tagged" for r in results)

    def test_finds_frontmatter_tag(self, engine, vault_path):
        write_note(vault_path, "fm.md", "---\ntags: [python]\n---\nbody")
        results = engine.tag_search("python")
        assert any(r.name == "fm" for r in results)

    def test_hash_prefix_stripped(self, engine, vault_path):
        write_note(vault_path, "t.md", "#mytag")
        assert len(engine.tag_search("#mytag")) == 1

    def test_no_match(self, engine, vault_path):
        write_note(vault_path, "a.md", "#other")
        assert engine.tag_search("python") == []


# ---------------------------------------------------------------------------
# metadata_search
# ---------------------------------------------------------------------------

class TestMetadataSearch:
    def test_finds_by_key_only(self, engine, vault_path):
        write_note(vault_path, "a.md", "---\nstatus: done\n---\n")
        write_note(vault_path, "b.md", "no frontmatter")
        results = engine.metadata_search("status")
        assert any(r.name == "a" for r in results)
        assert all(r.name != "b" for r in results)

    def test_finds_by_key_and_scalar_value(self, engine, vault_path):
        write_note(vault_path, "done.md", "---\nstatus: done\n---\n")
        write_note(vault_path, "todo.md", "---\nstatus: todo\n---\n")
        results = engine.metadata_search("status", value="done")
        names = [r.name for r in results]
        assert "done" in names
        assert "todo" not in names

    def test_value_match_is_case_insensitive(self, engine, vault_path):
        write_note(vault_path, "a.md", "---\nstatus: DONE\n---\n")
        results = engine.metadata_search("status", value="done")
        assert len(results) == 1

    def test_finds_value_in_list(self, engine, vault_path):
        write_note(vault_path, "a.md", "---\ntags: [python, django]\n---\n")
        results = engine.metadata_search("tags", value="python")
        assert len(results) == 1

    def test_no_match_returns_empty(self, engine, vault_path):
        write_note(vault_path, "a.md", "---\ntitle: X\n---\n")
        assert engine.metadata_search("nonexistent_key") == []


# ---------------------------------------------------------------------------
# link_search
# ---------------------------------------------------------------------------

class TestLinkSearch:
    def test_finds_note_with_wikilink(self, engine, vault_path):
        write_note(vault_path, "source.md", "See [[target]] for more")
        write_note(vault_path, "target.md", "I am target")
        results = engine.link_search("target")
        assert any(r.name == "source" for r in results)

    def test_md_extension_stripped(self, engine, vault_path):
        write_note(vault_path, "source.md", "See [[target]]")
        results = engine.link_search("target.md")
        assert any(r.name == "source" for r in results)

    def test_no_links_returns_empty(self, engine, vault_path):
        write_note(vault_path, "a.md", "no wikilinks here")
        assert engine.link_search("target") == []
