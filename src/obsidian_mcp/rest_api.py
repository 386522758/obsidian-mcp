"""Obsidian Local REST API client.

Requires the 'Obsidian Local REST API' community plugin.
Falls back gracefully when the plugin is not available.
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx

from .config import ObsidianConfig


class ObsidianAPIError(Exception):
    """Error from the Obsidian REST API."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Obsidian API error {status}: {message}")


class ObsidianRestAPI:
    """Client for Obsidian Local REST API plugin.

    Plugin: https://github.com/coddingtonbear/obsidian-local-rest-api
    """

    def __init__(self, config: ObsidianConfig) -> None:
        self.config = config
        self.base_url = config.rest_api_url.rstrip("/")
        self._headers: dict[str, str] = {"Accept": "application/json"}
        if config.rest_api_token:
            self._headers["Authorization"] = f"Bearer {config.rest_api_token}"
        # Obsidian Local REST API uses a self-signed cert
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            transport = httpx.HTTPTransport(verify=False)
            self._client = httpx.Client(
                transport=transport,
                timeout=10.0,
            )
        return self._client

    def is_available(self) -> bool:
        """Check if the REST API is reachable."""
        try:
            resp = self._get_client().get(
                f"{self.base_url}/",
                headers=self._headers,
            )
            return resp.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def get_file(self, path: str) -> str:
        """Get file content via REST API."""
        resp = self._get_client().get(
            f"{self.base_url}/vault/{path}",
            headers={**self._headers, "Accept": "text/plain"},
        )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.text

    def put_file(self, path: str, content: str) -> dict[str, Any]:
        """Create or update a file via REST API."""
        resp = self._get_client().put(
            f"{self.base_url}/vault/{path}",
            headers={**self._headers, "Content-Type": "text/markdown"},
            content=content,
        )
        if resp.status_code not in (200, 201, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "path": path}

    def delete_file(self, path: str) -> bool:
        """Delete a file via REST API."""
        resp = self._get_client().delete(
            f"{self.base_url}/vault/{path}",
            headers=self._headers,
        )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, context_length: int = 100) -> list[dict[str, Any]]:
        """Full-text search via REST API (uses Obsidian's search)."""
        resp = self._get_client().post(
            f"{self.base_url}/search/simple/",
            headers=self._headers,
            params={"query": query, "contextLength": context_length},
        )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.json().get("results", [])

    # ------------------------------------------------------------------
    # Periodic notes / commands
    # ------------------------------------------------------------------

    def list_commands(self) -> list[dict[str, str]]:
        """List available Obsidian commands."""
        resp = self._get_client().get(
            f"{self.base_url}/commands/",
            headers=self._headers,
        )
        if resp.status_code != 200:
            raise ObsidianAPIError(resp.status_code, resp.text)
        return resp.json().get("commands", [])

    def execute_command(self, command_id: str) -> dict[str, Any]:
        """Execute an Obsidian command by ID."""
        resp = self._get_client().post(
            f"{self.base_url}/commands/{command_id}",
            headers=self._headers,
        )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "command": command_id}

    # ------------------------------------------------------------------
    # Open notes in Obsidian
    # ------------------------------------------------------------------

    def open_note(self, path: str) -> dict[str, Any]:
        """Open a note in the Obsidian app."""
        resp = self._get_client().post(
            f"{self.base_url}/open/{path}",
            headers=self._headers,
        )
        if resp.status_code not in (200, 204):
            raise ObsidianAPIError(resp.status_code, resp.text)
        return {"status": "ok", "opened": path}

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()
