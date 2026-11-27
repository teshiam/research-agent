"""The agent loop: plan, then (decide -> act -> observe) within hard budgets, then write.

Everything the agent does is recorded as a step, so a run is fully inspectable afterwards.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import repo
from ..config import settings
from ..models import DEPTHS, FinishAction, ReadAction, SearchAction
from ..tools import fetch as fetch_tool
from ..tools import search as search_tool
from .policy import Policy, make_policy
from .state import Source, State, Usage
from .text import keywords, select_excerpts


class ToolError(RuntimeError):
    pass


@dataclass
class Deps:
    search: search_tool.SearchProvider
    fetch: Callable[[str], fetch_tool.Page]
    policy: Policy


def default_deps() -> Deps:
    return Deps(search=search_tool.get_search(), fetch=fetch_tool.fetch_page, policy=make_policy())


class _Recorder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.idx = 0
        self.usage = Usage()
        self.searches = 0
        self.pages = 0

    def step(
        self, kind: str, title: str, detail: dict[str, Any], started: float, usage: Usage
    ) -> None:
        repo.add_step(
            self.run_id, self.idx, kind, title, detail,
            duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        )  # fmt: skip
        self.idx += 1
        self.add_usage(usage)

    def add_usage(self, usage: Usage) -> None:
        self.usage = self.usage + usage
        repo.update_run(
            self.run_id,
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
            searches=self.searches,
            pages_read=self.pages,
        )


def _act_search(action: SearchAction, state: State, deps: Deps) -> dict[str, Any]:
    state.last_results = []  # a failed search must never leave stale results to read
    results = deps.search.search(action.query, 5)
    state.last_query = action.query
    state.last_results = results
    state.known.update({r.url: r for r in results})
    return {"query": action.query, "results": [r.__dict__ for r in results]}


def _act_read(action: ReadAction, state: State, deps: Deps) -> dict[str, Any]:
    url = action.url
    if url not in state.known:
        raise ToolError("That URL was not in the search results, so it was not read.")
    if url in state.seen:
        raise ToolError("That page was already read.")
    state.seen.add(url)  # mark first so a failing page is never retried
    page = deps.fetch(url)
    focus = keywords(f"{state.last_query} {state.topic}")
    excerpts = select_excerpts(page.text, focus, k=4)
    if not excerpts:
        raise ToolError("The page had no readable text.")
    focus_label = next((p.label for p in state.plan if p.query == state.last_query), "Findings")
    state.sources.append(
        Source(
            n=len(state.sources) + 1,
            title=page.title or state.known[url].title,
            url=url,
            focus=focus_label,
            excerpts=excerpts,
        )
    )
    return {"url": url, "title": page.title, "chars": len(page.text), "excerpts": excerpts}


def run_agent(run_id: str) -> None:
    run = repo.get_run(run_id)
    if run is None or run["status"] != "queued":
        return
    repo.touch_started(run_id)
    budget = DEPTHS[run["depth"]]
    rec = _Recorder(run_id)
    deadline = time.monotonic() + settings.run_timeout_seconds
    state = State(topic=run["topic"])

    try:
        deps = default_deps()

        t0 = time.monotonic()
        state.plan = deps.policy.plan(state.topic, budget.pages)
        rec.step("plan", f"Planned {len(state.plan)} research questions",
                 {"questions": [p.query for p in state.plan]}, t0, deps.policy.drain_usage())  # fmt: skip

        actions = 0
        stop_reason = ""
        carried = Usage()  # tokens spent on decisions that produce no step of their own
        while actions < budget.steps:
            if repo.is_cancel_requested(run_id):
                repo.touch_finished(run_id, "cancelled")
                return
            if time.monotonic() > deadline:
                stop_reason = "Stopped early: time limit reached."
                break
            if rec.usage.input_tokens + rec.usage.output_tokens > settings.max_total_tokens:
                stop_reason = "Stopped early: token budget reached."
                break
            if state.sources and len(state.sources) >= budget.pages:
                break

            state.pages_left = budget.pages - len(state.sources)
            state.steps_left = budget.steps - actions
            t0 = time.monotonic()
            action = deps.policy.next_action(state)
            usage = deps.policy.drain_usage()
            if isinstance(action, FinishAction):
                carried = carried + usage
                break
            actions += 1

            try:
                if isinstance(action, SearchAction):
                    rec.searches += 1
                    detail = _act_search(action, state, deps)
                    rec.step("search", f"Searched “{action.query}”", detail, t0, usage)
                else:
                    detail = _act_read(action, state, deps)
                    rec.pages = len(state.sources)
                    rec.step("read", f"Read {detail['title'] or action.url}", detail, t0, usage)
            except (search_tool.SearchError, fetch_tool.FetchError, ToolError) as exc:
                # Tool failures are normal. Record them and let the agent adapt.
                rec.step("error", str(exc), {"action": action.model_dump()}, t0, usage)

        if stop_reason:
            rec.step("note", stop_reason, {}, time.monotonic(), Usage())
        if repo.is_cancel_requested(run_id):
            rec.add_usage(carried)
            repo.touch_finished(run_id, "cancelled")
            return
        if not state.sources:
            rec.add_usage(carried)
            repo.touch_finished(run_id, "error", error="No usable sources could be read.")
            return

        t0 = time.monotonic()
        report = deps.policy.write(state)
        rec.step("write", f"Wrote report from {len(state.sources)} sources",
                 {"sources": len(state.sources), "chars": len(report)}, t0,
                 deps.policy.drain_usage() + carried)  # fmt: skip
        repo.touch_finished(run_id, "done", report=report)
    except Exception as exc:  # never leave a run stuck in "running"
        repo.touch_finished(run_id, "error", error=str(exc)[:300])
