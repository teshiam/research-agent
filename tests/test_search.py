import sys
import types

import httpx
import pytest

from app.config import settings
from app.tools.search import (
    DuckDuckGoSearch,
    SearchError,
    SearxngSearch,
    WikipediaSearch,
    get_search,
)


def test_wikipedia_results_are_parsed_and_urls_built():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        seen["ua"] = request.headers["user-agent"]
        rows = [{"title": "Solid-state battery", "snippet": 'A <span class="searchmatch">battery</span> type'}]
        return httpx.Response(200, json={"query": {"search": rows}})

    (result,) = WikipediaSearch(httpx.MockTransport(handler)).search("solid state battery", 3)
    assert result.url == "https://en.wikipedia.org/wiki/Solid-state_battery"
    assert result.snippet == "A battery type"
    assert seen["params"]["srsearch"] == "solid state battery" and seen["params"]["srlimit"] == "3"
    assert "ResearchAgent" in seen["ua"]


def test_wikipedia_errors_become_search_errors():
    with pytest.raises(SearchError):
        WikipediaSearch(httpx.MockTransport(lambda r: httpx.Response(500))).search("x")
    with pytest.raises(SearchError):
        WikipediaSearch(httpx.MockTransport(lambda r: httpx.Response(200, json={}))).search("x")


def test_searxng_results():
    body = {"results": [{"title": "T", "url": "https://a.example/x", "content": "<b>hi</b>"}, {"title": "no url"}]}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    (result,) = SearxngSearch("https://searx.example/", transport).search("q")
    assert (result.url, result.snippet) == ("https://a.example/x", "hi")


def test_duckduckgo_adapter_maps_fields(monkeypatch):
    class FakeDDGS:
        def text(self, query, max_results):
            return [{"title": "T", "href": "https://a.example", "body": "B"}, {"title": "skip"}]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    (result,) = DuckDuckGoSearch().search("q")
    assert (result.title, result.url, result.snippet) == ("T", "https://a.example", "B")


def test_duckduckgo_missing_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "ddgs", None)
    with pytest.raises(SearchError, match="pip install"):
        DuckDuckGoSearch().search("q")


def test_get_search_selects_provider(monkeypatch):
    assert isinstance(get_search(), WikipediaSearch)
    monkeypatch.setattr(settings, "search_provider", "searxng")
    with pytest.raises(SearchError, match="SEARXNG_URL"):
        get_search()
    monkeypatch.setattr(settings, "searxng_url", "https://s.example")
    assert isinstance(get_search(), SearxngSearch)
