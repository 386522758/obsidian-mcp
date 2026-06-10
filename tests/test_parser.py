"""Tests for the Obsidian markdown parser."""

import pytest
from obsidian_mcp.parser import (
    parse_frontmatter,
    extract_wikilinks,
    extract_tags,
    extract_embeds,
    extract_callouts,
    parse_note,
    build_frontmatter,
    update_frontmatter,
    make_wikilink,
)


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_no_frontmatter(self):
        meta, body = parse_frontmatter("Hello world")
        assert meta == {}
        assert body == "Hello world"

    def test_simple_frontmatter(self):
        content = "---\ntitle: My Note\ntags: [a, b]\n---\nBody text"
        meta, body = parse_frontmatter(content)
        assert meta["title"] == "My Note"
        assert meta["tags"] == ["a", "b"]
        assert body == "Body text"

    def test_empty_frontmatter_block(self):
        content = "---\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta == {}

    def test_frontmatter_only_no_body(self):
        content = "---\ntitle: Solo\n---\n"
        meta, body = parse_frontmatter(content)
        assert meta["title"] == "Solo"
        assert body == ""

    def test_malformed_yaml_returns_empty(self):
        content = "---\n: bad: yaml: [\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta == {}

    def test_yaml_non_dict_returns_empty(self):
        """YAML that parses to a non-dict (e.g. a list) is rejected."""
        content = "---\n- item1\n- item2\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta == {}

    def test_unclosed_frontmatter(self):
        content = "---\ntitle: oops\nBody"
        meta, body = parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_frontmatter_with_multiline_value(self):
        content = "---\ndescription: |\n  line one\n  line two\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert "line one" in meta["description"]


# ---------------------------------------------------------------------------
# extract_wikilinks
# ---------------------------------------------------------------------------

class TestExtractWikilinks:
    def test_plain_wikilink(self):
        links = extract_wikilinks("See [[MyNote]] for details")
        assert links == [{"target": "MyNote", "display": "MyNote"}]

    def test_aliased_wikilink(self):
        links = extract_wikilinks("See [[MyNote|click here]]")
        assert links == [{"target": "MyNote", "display": "click here"}]

    def test_folder_path_wikilink(self):
        links = extract_wikilinks("[[folder/SubNote]]")
        assert links[0]["target"] == "folder/SubNote"

    def test_multiple_wikilinks(self):
        links = extract_wikilinks("[[A]] and [[B|bee]]")
        assert len(links) == 2
        assert links[0]["target"] == "A"
        assert links[1]["target"] == "B"

    def test_embed_is_excluded(self):
        """![[image.png]] should not appear in wikilinks."""
        links = extract_wikilinks("![[image.png]] and [[RealLink]]")
        assert len(links) == 1
        assert links[0]["target"] == "RealLink"

    def test_no_wikilinks(self):
        assert extract_wikilinks("plain text") == []


# ---------------------------------------------------------------------------
# extract_tags
# ---------------------------------------------------------------------------

class TestExtractTags:
    def test_inline_tag(self):
        tags = extract_tags("Hello #project/work today")
        assert "project/work" in tags

    def test_tags_are_lowercased(self):
        tags = extract_tags("#Python #PYTHON #python")
        assert tags == ["python"]

    def test_deduplication(self):
        tags = extract_tags("#foo #bar #foo")
        assert tags.count("foo") == 1

    def test_tag_not_preceded_by_word_char(self):
        """e.g. url#anchor should not produce a tag."""
        tags = extract_tags("http://example.com#section")
        assert "section" not in tags

    def test_no_tags(self):
        assert extract_tags("no tags here") == []


# ---------------------------------------------------------------------------
# extract_embeds / extract_callouts
# ---------------------------------------------------------------------------

class TestExtractEmbeds:
    def test_embed(self):
        embeds = extract_embeds("![[diagram.png]]")
        assert embeds == ["diagram.png"]

    def test_no_embeds(self):
        assert extract_embeds("[[link]]") == []


class TestExtractCallouts:
    def test_callout(self):
        content = "> [!NOTE] Remember this"
        callouts = extract_callouts(content)
        assert callouts == [{"type": "NOTE", "title": "Remember this"}]

    def test_no_callouts(self):
        assert extract_callouts("regular text") == []


# ---------------------------------------------------------------------------
# parse_note (integration)
# ---------------------------------------------------------------------------

class TestParseNote:
    def test_full_note(self):
        content = (
            "---\ntitle: Test\ntags: [python]\n---\n"
            "Body with [[OtherNote]] and #inline-tag"
        )
        note = parse_note(content)
        assert note.frontmatter["title"] == "Test"
        assert note.has_frontmatter
        assert "python" in note.tags
        assert "inline-tag" in note.tags
        assert any(l["target"] == "OtherNote" for l in note.wikilinks)

    def test_note_without_frontmatter(self):
        note = parse_note("Just some text")
        assert not note.has_frontmatter
        assert note.frontmatter == {}
        assert note.body == "Just some text"

    def test_title_from_file_path(self, tmp_path):
        from pathlib import Path
        p = tmp_path / "My Note.md"
        p.write_text("content", encoding="utf-8")
        note = parse_note("content", file_path=p)
        assert note.title == "My Note"

    def test_title_from_frontmatter_takes_priority(self, tmp_path):
        from pathlib import Path
        p = tmp_path / "filename.md"
        p.write_text("", encoding="utf-8")
        note = parse_note("---\ntitle: FM Title\n---\n", file_path=p)
        assert note.title == "FM Title"

    def test_frontmatter_tags_list_merged_with_inline(self):
        content = "---\ntags: [alpha, beta]\n---\n#gamma"
        note = parse_note(content)
        assert "alpha" in note.tags
        assert "beta" in note.tags
        assert "gamma" in note.tags

    def test_frontmatter_tags_string_merged(self):
        content = "---\ntags: single\n---\n"
        note = parse_note(content)
        assert "single" in note.tags


# ---------------------------------------------------------------------------
# build_frontmatter / update_frontmatter
# ---------------------------------------------------------------------------

class TestBuildFrontmatter:
    def test_basic(self):
        result = build_frontmatter({"title": "X", "count": 1})
        assert result.startswith("---\n")
        assert "title: X" in result
        assert result.rstrip().endswith("---")

    def test_empty_dict_returns_empty_string(self):
        assert build_frontmatter({}) == ""

    def test_roundtrip(self):
        original = {"title": "Test", "tags": ["a", "b"], "done": False}
        rebuilt = build_frontmatter(original)
        meta, _ = parse_frontmatter(rebuilt + "body")
        assert meta["title"] == "Test"
        assert meta["tags"] == ["a", "b"]
        assert meta["done"] is False


class TestUpdateFrontmatter:
    def test_adds_new_key(self):
        content = "---\ntitle: Old\n---\nBody"
        result = update_frontmatter(content, {"status": "done"})
        meta, body = parse_frontmatter(result)
        assert meta["status"] == "done"
        assert meta["title"] == "Old"
        assert "Body" in body

    def test_overwrites_existing_key(self):
        content = "---\ntitle: Old\n---\nBody"
        result = update_frontmatter(content, {"title": "New"})
        meta, _ = parse_frontmatter(result)
        assert meta["title"] == "New"

    def test_body_preserved(self):
        content = "---\ntitle: T\n---\nKeep this body intact."
        result = update_frontmatter(content, {"x": 1})
        assert "Keep this body intact." in result

    def test_note_without_frontmatter_gets_new_fm(self):
        content = "No frontmatter here."
        result = update_frontmatter(content, {"key": "val"})
        meta, _ = parse_frontmatter(result)
        assert meta["key"] == "val"


# ---------------------------------------------------------------------------
# make_wikilink
# ---------------------------------------------------------------------------

class TestMakeWikilink:
    def test_plain(self):
        assert make_wikilink("Note") == "[[Note]]"

    def test_with_display(self):
        assert make_wikilink("Note", "click") == "[[Note|click]]"

    def test_display_same_as_target_omitted(self):
        assert make_wikilink("Note", "Note") == "[[Note]]"
