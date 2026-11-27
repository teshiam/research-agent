import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from ..config import settings


class SearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


class WikipediaSearch:
    """Free, keyless, stable: the official MediaWiki search API."""

    URL = "https://en.wikipedia.org/w/api.php"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        params = {"action": "query", "list": "search", "srsearch": query, "srlimit": limit,
                  "format": "json", "utf8": 1}  # fmt: skip
        try:
            with httpx.Client(
                timeout=15, headers={"User-Agent": settings.user_agent}, transport=self._transport
            ) as client:
                res = client.get(self.URL, params=params)
                res.raise_for_status()
                rows = res.json()["query"]["search"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise SearchError(f"Wikipedia search failed: {exc}") from exc
        return [
            SearchResult(
                title=r["title"],
                url="https://en.wikipedia.org/wiki/" + quote(r["title"].replace(" ", "_")),
                snippet=_plain(r.get("snippet", "")),
            )
            for r in rows
        ]


class DuckDuckGoSearch:
    """Web-wide search with no API key via the optional `ddgs` package (scrapes; may rate-limit)."""

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise SearchError('Install the extra first: pip install -e ".[ddg]"') from exc
        try:
            rows = DDGS().text(query, max_results=limit)
        except Exception as exc:
            raise SearchError(f"DuckDuckGo search failed: {exc}") from exc
        return [
            SearchResult(r.get("title", ""), r["href"], r.get("body", ""))
            for r in rows
            if r.get("href")
        ]


class SearxngSearch:
    """Self-hosted metasearch. The instance must have the JSON output format enabled."""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._transport = transport

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            with httpx.Client(
                timeout=15, headers={"User-Agent": settings.user_agent}, transport=self._transport
            ) as client:
                res = client.get(f"{self._base}/search", params={"q": query, "format": "json"})
                res.raise_for_status()
                rows = res.json()["results"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise SearchError(f"SearXNG search failed: {exc}") from exc
        return [
            SearchResult(r.get("title", ""), r["url"], _plain(r.get("content", "")))
            for r in rows[:limit]
            if r.get("url")
        ]


def get_search() -> SearchProvider:
    if settings.search_provider == "duckduckgo":
        return DuckDuckGoSearch()
    if settings.search_provider == "searxng":
        if not settings.searxng_url:
            raise SearchError("SEARXNG_URL is not set.")
        return SearxngSearch(settings.searxng_url)
    return WikipediaSearch()
