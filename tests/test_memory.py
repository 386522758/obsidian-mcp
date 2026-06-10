"""Tests for UnifiedMemoryStore – save, recall, lifecycle, merge."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from obsidian_mcp.config import ObsidianConfig
from obsidian_mcp.vault import Vault
from obsidian_mcp.memory import (
    UnifiedMemoryStore,
    _content_hash,
    _safe_title,
    _agent_folder,
    DECAY_DAYS,
    ARCHIVE_AFTER_DAYS,
    MIN_IMPORTANCE,
    MAX_IMPORTANCE,
)


@pytest.fixture
def store(config: ObsidianConfig, vault: Vault) -> UnifiedMemoryStore:
    s = UnifiedMemoryStore(config, vault)
    s._ensure_folders()
    return s


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_same_content_same_hash(self):
        assert _content_hash("hello world") == _content_hash("hello world")

    def test_whitespace_normalised(self):
        assert _content_hash("hello  world") == _content_hash("hello world")

    def test_case_normalised(self):
        assert _content_hash("Hello World") == _content_hash("hello world")

    def test_different_content_different_hash(self):
        assert _content_hash("foo") != _content_hash("bar")


class TestSafeTitle:
    def test_alphanumeric_unchanged(self):
        assert _safe_title("hello world") == "hello world"

    def test_special_chars_replaced(self):
        result = _safe_title("foo/bar?baz")
        assert "/" not in result
        assert "?" not in result

    def test_truncates_to_max_len(self):
        long = "a" * 100
        assert len(_safe_title(long, max_len=60)) <= 60

    def test_empty_string_returns_untitled(self):
        assert _safe_title("") == "untitled"

    def test_all_special_chars_returns_underscores_not_untitled(self):
        # "???" becomes "___" after substitution — truthy, so not "untitled"
        result = _safe_title("???")
        assert result != ""
        assert "?" not in result


class TestAgentFolder:
    def test_known_agents_route_correctly(self):
        assert _agent_folder("claude") == "claude"
        assert _agent_folder("codex") == "codex"
        assert _agent_folder("cursor") == "cursor"

    def test_unknown_agent_goes_to_shared(self):
        assert _agent_folder("gpt4") == "shared"

    def test_case_insensitive(self):
        assert _agent_folder("Claude") == "claude"

    def test_comma_separated_takes_first(self):
        assert _agent_folder("claude,codex") == "claude"


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------

class TestSaveMemory:
    def test_saves_new_memory(self, store, vault_path):
        result = store.save_memory("My first memory", title="First")
        assert result["memory_id"].startswith("mem-")
        assert result["dedup"] is False

    def test_deduplication_returns_existing(self, store):
        r1 = store.save_memory("duplicate content", title="Dup")
        r2 = store.save_memory("duplicate content", title="Dup")
        assert r2["memory_id"] == r1["memory_id"]
        assert r2.get("dedup") is True

    def test_whitespace_normalised_for_dedup(self, store):
        r1 = store.save_memory("same   content", title="T")
        r2 = store.save_memory("same content", title="T")
        assert r1["memory_id"] == r2["memory_id"]

    def test_importance_clamped_to_max(self, store):
        result = store.save_memory("x", importance=99)
        assert result["importance"] == MAX_IMPORTANCE

    def test_importance_clamped_to_min(self, store):
        result = store.save_memory("x", importance=-5)
        assert result["importance"] == MIN_IMPORTANCE

    def test_agent_routes_to_correct_folder(self, store, vault_path):
        result = store.save_memory("hello", agent="claude")
        assert result["folder"] == "claude"

    def test_unknown_agent_routes_to_shared(self, store):
        result = store.save_memory("hello", agent="gpt4")
        assert result["folder"] == "shared"

    def test_auto_title_from_content(self, store):
        result = store.save_memory("Short content without explicit title")
        assert len(result["title"]) > 0

    def test_note_file_is_created(self, store, vault_path):
        result = store.save_memory("file check", title="FileCheck")
        path = vault_path / result["path"]
        assert path.exists()

    def test_related_notes_appear_in_body(self, store, vault_path):
        result = store.save_memory(
            "content", title="T", related_notes=["SomeNote"]
        )
        raw = (vault_path / result["path"]).read_text(encoding="utf-8")
        assert "[[SomeNote]]" in raw


# ---------------------------------------------------------------------------
# recall_memories
# ---------------------------------------------------------------------------

class TestRecallMemories:
    def test_recall_by_query(self, store):
        store.save_memory("Python is a great language", title="Python note")
        store.save_memory("Java is verbose", title="Java note")
        results = store.recall_memories(query="python")
        titles = [r["title"] for r in results]
        assert any("Python" in t for t in titles)

    def test_recall_without_query_returns_recent(self, store):
        store.save_memory("alpha", title="Alpha")
        store.save_memory("beta", title="Beta")
        results = store.recall_memories()
        assert len(results) >= 2

    def test_category_filter(self, store):
        store.save_memory("task memory", category="tasks")
        store.save_memory("idea memory", category="ideas")
        results = store.recall_memories(category="tasks")
        assert all(r["category"] == "tasks" for r in results)

    def test_agent_filter(self, store):
        store.save_memory("claude memory", agent="claude")
        store.save_memory("codex memory", agent="codex")
        results = store.recall_memories(agent="claude")
        assert all("claude" in r.get("agent", "") for r in results)

    def test_min_importance_filter(self, store):
        store.save_memory("low priority", importance=1)
        store.save_memory("high priority", importance=5)
        results = store.recall_memories(min_importance=4)
        assert all(r["importance"] >= 4 for r in results)

    def test_limit_respected(self, store):
        for i in range(10):
            store.save_memory(f"memory number {i}", title=f"Mem{i}")
        results = store.recall_memories(limit=3)
        assert len(results) <= 3

    def test_archived_excluded_by_default(self, store):
        r = store.save_memory("to archive", title="Archive me")
        mem_id = r["memory_id"]
        store.archive_memory(mem_id)
        results = store.recall_memories()
        assert all(res.get("status") != "archived" for res in results)

    def test_archived_included_when_flag_set(self, store):
        r = store.save_memory("to archive", title="Archive me2")
        store.archive_memory(r["memory_id"])
        results = store.recall_memories(include_archived=True)
        statuses = [res.get("status") for res in results]
        assert "archived" in statuses


# ---------------------------------------------------------------------------
# forget_memory / archive_memory
# ---------------------------------------------------------------------------

class TestForgetMemory:
    def test_forget_by_memory_id(self, store, vault_path):
        r = store.save_memory("forget me", title="Forget")
        success = store.forget_memory(r["memory_id"])
        assert success is True
        assert not (vault_path / r["path"]).exists()

    def test_forget_by_path(self, store, vault_path):
        r = store.save_memory("forget by path", title="ByPath")
        success = store.forget_memory(r["path"])
        assert success is True

    def test_forget_nonexistent_id_returns_false(self, store):
        assert store.forget_memory("mem-nonexistent") is False


class TestArchiveMemory:
    def test_archive_moves_to_archive_folder(self, store, vault_path):
        r = store.save_memory("archive me", title="Archive")
        mem_id = r["memory_id"]
        result = store.archive_memory(mem_id)
        assert result is True
        archive_dir = vault_path / store.archive_folder
        assert any(archive_dir.rglob("*.md"))

    def test_archived_note_has_status_archived(self, store, vault_path):
        r = store.save_memory("check status", title="StatusCheck")
        store.archive_memory(r["memory_id"])
        archive_dir = vault_path / store.archive_folder
        notes = list(archive_dir.rglob("*.md"))
        assert len(notes) > 0
        content = notes[0].read_text(encoding="utf-8")
        assert "archived" in content

    def test_archive_nonexistent_returns_false(self, store):
        assert store.archive_memory("mem-does-not-exist") is False


# ---------------------------------------------------------------------------
# merge_memories
# ---------------------------------------------------------------------------

class TestMergeMemories:
    def test_merge_creates_new_memory(self, store):
        r1 = store.save_memory("first memory content", title="First")
        r2 = store.save_memory("second memory content", title="Second")
        result = store.merge_memories(
            [r1["memory_id"], r2["memory_id"]],
            merged_content="Combined content",
            title="Merged",
        )
        assert result["merged"] is True
        assert result["merged_count"] == 2
        assert result["new_memory_id"].startswith("mem-")

    def test_merge_archives_originals(self, store, vault_path):
        r1 = store.save_memory("orig one", title="O1")
        r2 = store.save_memory("orig two", title="O2")
        result = store.merge_memories(
            [r1["memory_id"], r2["memory_id"]],
            merged_content="merged",
        )
        archive_dir = vault_path / store.archive_folder
        archived = list(archive_dir.rglob("*.md"))
        assert len(archived) == 2

    def test_merge_requires_at_least_two(self, store):
        r = store.save_memory("lone memory", title="Lone")
        with pytest.raises(ValueError, match="at least 2"):
            store.merge_memories([r["memory_id"]], merged_content="x")

    def test_merge_raises_if_no_valid_memories(self, store):
        with pytest.raises(ValueError, match="No valid"):
            store.merge_memories(["mem-fake1", "mem-fake2"], merged_content="x")


# ---------------------------------------------------------------------------
# run_lifecycle – decay and archive
# ---------------------------------------------------------------------------

class TestRunLifecycle:
    def _save_old_memory(self, store, vault_path, days_old: int, importance: int, title: str) -> dict:
        """Save a memory then backdated its last_accessed in the frontmatter."""
        r = store.save_memory(f"content for {title}", title=title, importance=importance)
        old_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        store.vault.update_note(
            r["path"],
            frontmatter_updates={"last_accessed": old_date, "created": old_date},
        )
        return r

    def test_no_lifecycle_changes_for_fresh_memory(self, store, vault_path):
        store.save_memory("fresh", title="Fresh", importance=3)
        result = store.run_lifecycle()
        assert result["decayed"] == 0
        assert result["archived"] == 0

    def test_old_high_importance_memory_decays(self, store, vault_path):
        self._save_old_memory(store, vault_path, days_old=DECAY_DAYS + 5, importance=3, title="OldHigh")
        result = store.run_lifecycle()
        assert result["decayed"] >= 1

    def test_old_min_importance_memory_gets_archived(self, store, vault_path):
        self._save_old_memory(
            store, vault_path,
            days_old=ARCHIVE_AFTER_DAYS + 5,
            importance=MIN_IMPORTANCE,
            title="OldMin",
        )
        result = store.run_lifecycle()
        assert result["archived"] >= 1
