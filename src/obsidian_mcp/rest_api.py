"""Obsidian Local REST API client.

Requires the 'Obsidian Local REST API' community plugin.
Falls back gracefully when the plugin is not available.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import ObsidianConfig

# Obsidian Local REST API uses a self-signed certificate; verification is
# intentionally disabled for localhost-only communication.
_SSL_VERIFY = False


class ObsidianAPIError(Exception):
    """Error from the Obsidian REST API."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Obsidian API error {status}: {message}")


class ObsidianRestAPI:
    """Async client for Obsidian Local REST API plugin.

    Plugin: https://github.com/coddingtonbear/obsidian-local-rest-api
    """

    def __init__(self, config: ObsidianConfig) -> None:
        self.config = config
        self.base_url = config.rest_api_url.rstrip("/")
        self._headers: dict[str, str] = {"Accept": "application/json"}
        if config.rest_api_token:
            self._headers["Authorization"] = f"Bearer {config.rest_api_token}"

    def _client(self) -> httpx.AsyncClient:
        """Return a new async HTTP client (used as an async context manager)."""
        return httpx.AsyncClient(verify=_SSL_VERIFY, timeout=10.0)

    async def is_available(self) -> bool:
        """Check if the REST API is reachable."""
        try:
            async with self._client() as client:
                resp = await client.get(f"{self.base_url}/", headers=self._headers)
                return resp.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def get_file(self, path: str) -> str:
        """Get file content via REST API."""
        async with self._client() as client:
            resp = await client.get(
                f"{self.base_url}/vault/{path}",
                headers={**self._headers, "Accept": "text/plain"},
            )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.text

    async def put_file(self, path: str, content: str) -> dict[str, Any]:
        """Create or update a file via REST API."""
        async with self._client() as client:
            resp = await client.put(
                f"{self.base_url}/vault/{path}",
                headers={**self._headers, "Content-Type": "text/markdown"},
                content=content,
            )
        if resp.status_code not in (200, 201, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "path": path}

    async def delete_file(self, path: str) -> bool:
        """Delete a file via REST API."""
        async with self._client() as client:
            resp = await client.delete(
                f"{self.base_url}/vault/{path}",
                headers=self._headers,
            )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, context_length: int = 100) -> list[dict[str, Any]]:
        """Full-text search via REST API (uses Obsidian's search)."""
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/search/simple/",
                headers=self._headers,
                params={"query": query, "contextLength": context_length},
            )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.json().get("results", [])

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def list_commands(self) -> list[dict[str, str]]:
        """List available Obsidian commands."""
        async with self._client() as client:
            resp = await client.get(
                f"{self.base_url}/commands/",
                headers=self._headers,
            )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.json().get("commands", [])

    async def execute_command(self, command_id: str) -> dict[str, Any]:
        """Execute an Obsidian command by ID."""
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/commands/{command_id}",
                headers=self._headers,
            )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "command": command_id}

    # ------------------------------------------------------------------
    # Open notes in Obsidian
    # ------------------------------------------------------------------

    async def open_note(self, path: str) -> dict[str, Any]:
        """Open a note in the Obsidian app."""
        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/open/{path}",
                headers=self._headers,
            )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "opened": path}
