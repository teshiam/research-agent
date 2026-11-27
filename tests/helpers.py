import json
import re

from app.agent.loop import Deps
from app.agent.policy import HeuristicPolicy, LLMPolicy
from app.agent.state import Usage
from app.tools.fetch import FetchError, Page
from app.tools.search import SearchError, SearchResult

SENTENCES = (
    "Solid state batteries replace the liquid electrolyte with a solid material inside the cell. "
    "Researchers say this design can improve energy density and safety for electric vehicles. "
    "Manufacturing the solid electrolyte at scale remains an expensive engineering challenge today. "
    "Several automakers have announced pilot production lines for solid state battery packs."
)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class FakeSearch:
    """Returns two deterministic results per query; can be told to fail on certain queries."""

    def __init__(self, fail_on: tuple[str, ...] = ()) -> None:
        self.fail_on = fail_on
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        if any(f in query for f in self.fail_on):
            raise SearchError("search backend unavailable")
        base = f"https://example.org/{slug(query)}"
        return [
            SearchResult(f"Result A for {query}", f"{base}-a", "snippet a"),
            SearchResult(f"Result B for {query}", f"{base}-b", "snippet b"),
        ]


def good_fetch(url: str) -> Page:
    return Page(title=f"Page {url[-12:]}", url=url, text=SENTENCES)


def failing_fetch(url: str) -> Page:
    raise FetchError("The page returned HTTP 503.")


class Scripted:
    """A fake LLM: replays queued replies, then falls back to `default`. Records prompts."""

    def __init__(self, replies: list[str], default: str | None = None, usage=(100, 20)) -> None:
        self.replies = list(replies)
        self.default = default
        self.usage = Usage(*usage)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> tuple[str, Usage]:
        self.calls.append((system, user))
        if self.replies:
            return self.replies.pop(0), self.usage
        if self.default is None:
            raise AssertionError("Scripted LLM ran out of replies")
        return self.default, self.usage


def heuristic_deps(search=None, fetch=good_fetch) -> Deps:
    return Deps(search=search or FakeSearch(), fetch=fetch, policy=HeuristicPolicy())


def llm_deps(script: Scripted, search=None, fetch=good_fetch) -> Deps:
    return Deps(search=search or FakeSearch(), fetch=fetch, policy=LLMPolicy(script))


def action(**kw) -> str:
    return json.dumps(kw)
