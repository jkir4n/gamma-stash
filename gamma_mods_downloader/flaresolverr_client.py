"""
Flaresolverr client for the Gamma Mods Downloader.

Flaresolverr is a proxy server that bypasses Cloudflare challenges.
Run it via Docker:
  docker run -d --name flaresolverr -p 8191:8191 flaresolverr/flaresolverr
"""

import json
import re
import urllib.request
from typing import Optional


class FlaresolverrError(Exception):
    """Raised when Flaresolverr fails to resolve a page."""
    pass


class FlaresolverrClient:
    """Client for interacting with a Flaresolverr instance."""

    def __init__(self, url: str = "http://localhost:8191/v1", timeout_ms: int = 60000):
        self.url = url.rstrip("/")
        self.timeout_ms = timeout_ms

    def resolve(self, page_url: str, timeout_ms: Optional[int] = None) -> dict:
        """
        Resolve a Cloudflare-protected URL through Flaresolverr.

        Returns the full Flaresolverr response dict, including:
          - solution.response: HTML of the resolved page
          - solution.cookies: list of cookies
          - solution.userAgent: User-Agent string to use for subsequent requests

        Raises FlaresolverrError on failure.
        """
        payload = json.dumps({
            "cmd": "request.get",
            "url": page_url,
            "maxTimeout": timeout_ms or self.timeout_ms,
        }).encode()

        timeout = (timeout_ms or self.timeout_ms) // 1000 + 30
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = json.loads(resp.read())
        except Exception as e:
            raise FlaresolverrError(f"Failed to connect to Flaresolverr at {self.url}: {e}")

        if result.get("status") != "ok":
            msg = result.get("message", "Unknown error")
            raise FlaresolverrError(f"Flaresolverr request failed: {msg}")

        solution = result.get("solution")
        if not solution:
            raise FlaresolverrError("Flaresolverr returned no solution")

        return result

    def extract_mirror_url(self, html: str) -> Optional[str]:
        """
        Extract the ModDB mirror download URL from the mod page HTML.

        ModDB mirror URLs look like: /downloads/mirror/<hash>
        Returns the full URL (including https://www.moddb.com prefix).
        """
        match = re.search(r'href="(/downloads/mirror/[^"]+)"', html)
        if not match:
            return None
        return "https://www.moddb.com" + match.group(1)

    def extract_cookies(self, solution: dict) -> tuple[list[dict], str]:
        """Extract cookies and User-Agent from a Flaresolverr solution."""
        cookies = solution.get("cookies", [])
        user_agent = solution.get("userAgent", "")
        return cookies, user_agent

    def build_cookie_header(self, cookies: list[dict]) -> str:
        """Build a Cookie header string from Flaresolverr cookies."""
        parts = []
        for c in cookies:
            name = c.get("name", "").strip('"')
            value = c.get("value", "").strip('"')
            if name and value:
                parts.append(f"{name}={value}")
        return "; ".join(parts)
