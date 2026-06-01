# Changelog

All notable changes to obsidian-mcp will be documented in this file.

## [0.1.1] - 2026-06-01

### Fixed

- **MCP protocol compatibility**: Rewrote server to use `FastMCP` API instead of deprecated `Server` + `run_server`. The old API (`mcp.server.Server`, `mcp.server.stdio.run_server`) no longer exists in `mcp>=1.27`. Now uses `FastMCP` + `run_stdio_async()`.
- **Decorator syntax**: Changed `@self.server.tool` to `@self.server.tool()` — the `FastMCP.tool` decorator requires explicit call parentheses, matching the current MCP SDK contract.
- **Removed unused imports**: Cleaned up `Tool` import from `mcp.types` (not needed with `FastMCP`).
- **Removed resource registration**: The old `register_resources()` method used the `@server.resource()` pattern which is not compatible with `FastMCP`. Resources can be re-added using `FastMCP`'s `@server.resource()` decorator in a future release.

### Verified

- MCP server starts successfully on Windows (Python 3.14)
- All 25 tools register and respond correctly via JSON-RPC over stdio
- Full MCP handshake (initialize → initialized → tools/list) passes
- Tested with Codex desktop and Claude Desktop — both load all tools

## [0.1.0] - 2026-05-31

### Added

- Initial release of obsidian-mcp server
- 25 MCP tools for Obsidian vault operations
- Direct file-system access mode (no plugin required)
- Obsidian Local REST API client (optional, requires plugin)
- Note CRUD: read, create, update, delete, move
- Obsidian markdown parser: frontmatter, wikilinks, tags, embeds, callouts
- Full-text search with boolean operators (`+must-have`, `-exclude`)
- Tag search and frontmatter metadata search
- Backlink discovery and vault link graph analysis
- Template management with `{{variable}}` substitution
- Daily notes: get, create, append
- Memory/knowledge store for agent memories with category, importance, and recall
- Wikilink generator utility
- Vault statistics
- Bilingual README (English + Chinese)
- Comprehensive usage guide (USAGE.md)
