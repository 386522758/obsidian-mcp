"""Full-text and metadata search for Obsidian notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ObsidianConfig
from .parser import ParsedNote, parse_note


@dataclass
class SearchResult:
    """A single search result."""
    path: str
    name: str
    score: float = 0.0
    snippet: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class SearchEngine:
    """Simple but effective search over an Obsidian vault."""

    def __init__(self, config: ObsidianConfig) -> None:
        self.config = config
        self.root = config.vault_path.resolve()

    def _iter_notes(self):
        """Iterate over all non-hidden .md files."""
        for md_file in self.root.rglob("*.md"):
            rel = md_file.relative_to(self.root)
            if any(p.startswith(".") for p in rel.parts):
                continue
            yield md_file

    def fulltext_search(
        self,
        query: str,
        folder: str = "",
        limit: int = 20,
        case_sensitive: bool = False,
    ) -> list[SearchResult]:
        """Search note contents for a text query.
        
        Supports simple boolean: use +term for must-have, -term for exclusion.
        """
        results: list[SearchResult] = []
        query_lower = query.lower() if not case_sensitive else query
        terms = query_lower.split() if not case_sensitive else query.split()

        base = (self.root / folder).resolve() if folder else self.root

        for md_file in self._iter_notes():
            if folder:
                try:
                    md_file.relative_to(base)
                except ValueError:
                    continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            searchable = content if case_sensitive else content.lower()

            # Simple scoring: count occurrences of each term
            score = 0.0
            matched = True
            for term in terms:
                if term.startswith("-"):
                    if term[1:] in searchable:
                        matched = False
                        break
                elif term.startswith("+"):
                    count = searchable.count(term[1:])
                    if count == 0:
                        matched = False
                        break
                    score += count * 2  # boosted
                else:
                    count = searchable.count(term)
                    if count == 0:
                        matched = False
                        break
                    score += count

            if not matched or score == 0:
                continue

            # Build snippet around first match
            snippet = self._extract_snippet(content, terms[0] if terms else query, case_sensitive)

            rel_path = str(md_file.relative_to(self.root))
            note = parse_note(content, file_path=md_file)
            results.append(SearchResult(
                path=rel_path,
                name=md_file.stem,
                score=score,
                snippet=snippet,
                frontmatter=note.frontmatter,
                tags=note.tags,
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def tag_search(self, tag: str, limit: int = 50) -> list[SearchResult]:
        """Find all notes with a specific tag."""
        tag_lower = tag.lower().lstrip("#")
        results: list[SearchResult] = []

        for md_file in self._iter_notes():
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            note = parse_note(content, file_path=md_file)
            if tag_lower in note.tags:
                rel_path = str(md_file.relative_to(self.root))
                results.append(SearchResult(
                    path=rel_path,
                    name=md_file.stem,
                    frontmatter=note.frontmatter,
                    tags=note.tags,
                ))

            if len(results) >= limit:
                break
        return results

    def metadata_search(
        self,
        key: str,
        value: Any = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search notes by frontmatter key/value."""
        results: list[SearchResult] = []

        for md_file in self._iter_notes():
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            note = parse_note(content, file_path=md_file)
            if key not in note.frontmatter:
                continue
            if value is not None:
                fm_val = note.frontmatter[key]
                if isinstance(fm_val, list):
                    if value not in fm_val:
                        continue
                elif str(fm_val).lower() != str(value).lower():
                    continue

            rel_path = str(md_file.relative_to(self.root))
            results.append(SearchResult(
                path=rel_path,
                name=md_file.stem,
                frontmatter=note.frontmatter,
                tags=note.tags,
            ))

            if len(results) >= limit:
                break
        return results

    def link_search(self, note_name: str, limit: int = 50) -> list[SearchResult]:
        """Find notes that reference a given note via wikilinks."""
        from .parser import WIKILINK_RE
        results: list[SearchResult] = []
        target = note_name.replace(".md", "")

        for md_file in self._iter_notes():
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for match in WIKILINK_RE.finditer(content):
                link_target = match.group(1).strip().split("|")[0].strip()
                if link_target == target:
                    rel_path = str(md_file.relative_to(self.root))
                    note = parse_note(content, file_path=md_file)
                    results.append(SearchResult(
                        path=rel_path,
                        name=md_file.stem,
                        snippet=content[
                            max(0, match.start() - 80):match.end() + 80
                        ].replace("\n", " "),
                        frontmatter=note.frontmatter,
                        tags=note.tags,
                    ))
                    break

            if len(results) >= limit:
                break
        return results

    def _extract_snippet(
        self, content: str, term: str, case_sensitive: bool
    ) -> str:
        """Extract a snippet around the first match of a term."""
        searchable = content if case_sensitive else content.lower()
        idx = searchable.find(term if case_sensitive else term.lower())
        if idx == -1:
            return content[:200].replace("\n", " ")
        start = max(0, idx - 80)
        end = min(len(content), idx + len(term) + 80)
        snippet = content[start:end].replace("\n", " ")
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet
