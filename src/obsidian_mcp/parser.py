"""Obsidian markdown parser - frontmatter, wikilinks, tags, and more."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# Wikilink pattern: [[target]] or [[target|display text]]
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")

# Tag pattern: #tag or #nested/tag (not inside code blocks)
TAG_RE = re.compile(r"(?<!\w)#([\w][\w/\-]*)")

# Embedded file pattern: ![[file]]
EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")

# Callout pattern: > [!type] Title
CALLOUT_RE = re.compile(r"^\s*>\s*\[!(\w+)\]\s*(.*)", re.MULTILINE)


@dataclass
class ParsedNote:
    """Result of parsing an Obsidian markdown note."""

    # Raw content
    content: str = ""
    body: str = ""  # Content without frontmatter

    # Frontmatter metadata
    frontmatter: dict[str, Any] = field(default_factory=dict)
    has_frontmatter: bool = False

    # Extracted elements
    wikilinks: list[dict[str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    embeds: list[str] = field(default_factory=list)
    callouts: list[dict[str, str]] = field(default_factory=list)

    # File metadata
    title: str = ""
    file_path: Path | None = None
    created: datetime | None = None
    modified: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title and self.file_path:
            self.title = self.file_path.stem


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and return (metadata, body)."""
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return {}, content

    yaml_str = content[3:end_idx].strip()
    body = content[end_idx + 3:].lstrip("\n")

    if yaml and yaml_str:
        try:
            metadata = yaml.safe_load(yaml_str)
            if isinstance(metadata, dict):
                return metadata, body
        except yaml.YAMLError:
            pass

    return {}, content


def extract_wikilinks(content: str) -> list[dict[str, str]]:
    """Extract all wikilinks from content.
    
    Returns list of dicts with 'target' and 'display' keys.
    """
    links = []
    for match in WIKILINK_RE.finditer(content):
        target = match.group(1).strip()
        display = (match.group(2) or target).strip()
        # Skip embeds (handled separately)
        if content[max(0, match.start() - 1):match.start()] == "!":
            continue
        links.append({"target": target, "display": display})
    return links


def extract_tags(content: str) -> list[str]:
    """Extract tags from content and frontmatter."""
    tags = set()
    for match in TAG_RE.finditer(content):
        tag = match.group(1).lower()
        tags.add(tag)
    return sorted(tags)


def extract_embeds(content: str) -> list[str]:
    """Extract embedded file references."""
    return [m.group(1).strip() for m in EMBED_RE.finditer(content)]


def extract_callouts(content: str) -> list[dict[str, str]]:
    """Extract callout blocks."""
    return [
        {"type": m.group(1), "title": m.group(2).strip()}
        for m in CALLOUT_RE.finditer(content)
    ]


def parse_note(
    content: str,
    file_path: Path | None = None,
    file_stat: Any = None,
) -> ParsedNote:
    """Parse an Obsidian markdown note into structured data."""
    frontmatter, body = parse_frontmatter(content)

    # Extract tags from frontmatter + body
    tags = set(extract_tags(content))
    # Also check frontmatter tags field
    fm_tags = frontmatter.get("tags", [])
    if isinstance(fm_tags, str):
        tags.add(fm_tags.lower())
    elif isinstance(fm_tags, list):
        for t in fm_tags:
            if isinstance(t, str):
                tags.add(t.lower())

    created = None
    modified = None
    if file_stat:
        created = datetime.fromtimestamp(file_stat.st_ctime)
        modified = datetime.fromtimestamp(file_stat.st_mtime)

    return ParsedNote(
        content=content,
        body=body,
        frontmatter=frontmatter,
        has_frontmatter=bool(frontmatter),
        wikilinks=extract_wikilinks(content),
        tags=sorted(tags),
        embeds=extract_embeds(content),
        callouts=extract_callouts(content),
        title=frontmatter.get("title", "") or (file_path.stem if file_path else ""),
        file_path=file_path,
        created=created,
        modified=modified,
    )


def build_frontmatter(metadata: dict[str, Any]) -> str:
    """Build a YAML frontmatter string from metadata."""
    if not metadata:
        return ""
    if yaml:
        yaml_str = yaml.dump(metadata, allow_unicode=True, default_flow_style=False, sort_keys=False)
    else:
        # Fallback: simple key-value
        lines = []
        for k, v in metadata.items():
            if isinstance(v, list):
                lines.append(f"{k}: [{', '.join(str(i) for i in v)}]")
            elif isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            else:
                lines.append(f"{k}: {v}")
        yaml_str = "\n".join(lines)
    return f"---\n{yaml_str}---\n\n"


def update_frontmatter(content: str, updates: dict[str, Any]) -> str:
    """Update frontmatter fields, preserving existing body."""
    metadata, body = parse_frontmatter(content)
    metadata.update(updates)
    return build_frontmatter(metadata) + body


def make_wikilink(target: str, display: str | None = None) -> str:
    """Create a wikilink string."""
    if display and display != target:
        return f"[[{target}|{display}]]"
    return f"[[{target}]]"
