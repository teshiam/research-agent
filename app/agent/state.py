from dataclasses import dataclass, field

from ..tools.search import SearchResult


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True)
class PlanItem:
    label: str
    query: str


@dataclass
class Source:
    n: int
    title: str
    url: str
    focus: str
    excerpts: list[str]


@dataclass
class State:
    topic: str
    plan: list[PlanItem] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    last_query: str = ""
    last_results: list[SearchResult] = field(default_factory=list)
    known: dict[str, SearchResult] = field(default_factory=dict)  # every URL a search returned
    seen: set[str] = field(default_factory=set)  # URLs already read or attempted
    pages_left: int = 0
    steps_left: int = 0

    def unread(self) -> list[SearchResult]:
        return [r for r in self.last_results if r.url not in self.seen]
