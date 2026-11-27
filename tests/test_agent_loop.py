import json

from app import repo
from app.agent import loop
from app.agent.policy import finalize_report
from app.agent.state import Source, State
from app.config import settings

from .helpers import (
    FakeSearch,
    Scripted,
    action,
    failing_fetch,
    good_fetch,
    heuristic_deps,
    llm_deps,
)


def _start(topic="solid state batteries", depth="quick", mode="heuristic") -> str:
    run_id = repo.create_run(topic, depth, mode, "")
    loop.run_agent(run_id)
    return run_id


def _kinds(run_id):
    return [s["kind"] for s in repo.list_steps(run_id)]


# ------------------------------------------------------------------ heuristic (free) mode
def test_heuristic_run_plans_searches_reads_and_writes(use_deps):
    use_deps(heuristic_deps())
    run_id = _start()
    run = repo.get_run(run_id)

    assert run["status"] == "done" and run["error"] is None
    assert _kinds(run_id) == ["plan", "search", "read", "search", "read", "search", "read", "write"]
    assert (run["searches"], run["pages_read"]) == (3, 3)
    assert "Free mode report" in run["report"]
    assert "[1]" in run["report"] and "## Sources" in run["report"]
    assert run["started_at"] and run["finished_at"]
    assert run["input_tokens"] == 0 and run["cost_usd"] == 0


def test_heuristic_depth_changes_how_much_is_read(use_deps):
    use_deps(heuristic_deps())
    run_id = _start(depth="standard")
    assert repo.get_run(run_id)["pages_read"] == 5


def test_search_failure_is_recorded_and_the_run_continues(use_deps):
    use_deps(heuristic_deps(search=FakeSearch(fail_on=("history",))))
    run_id = _start()
    run = repo.get_run(run_id)
    errors = [s for s in repo.list_steps(run_id) if s["kind"] == "error"]
    assert run["status"] == "done" and run["pages_read"] == 2
    assert errors and "search backend unavailable" in errors[0]["title"]


def test_run_fails_clearly_when_nothing_can_be_read(use_deps):
    use_deps(heuristic_deps(fetch=failing_fetch))
    run_id = _start()
    run = repo.get_run(run_id)
    assert run["status"] == "error" and "No usable sources" in run["error"]
    assert "write" not in _kinds(run_id)


def test_unexpected_crash_marks_run_as_error_not_stuck(use_deps):
    def explode(url):
        raise RuntimeError("boom")

    use_deps(heuristic_deps(fetch=explode))
    run_id = _start()
    run = repo.get_run(run_id)
    assert run["status"] == "error" and "boom" in run["error"]


def test_cancel_during_run_stops_it(use_deps):
    def fetch_then_cancel(url):
        repo.request_cancel(repo.list_runs()[0]["id"])
        return good_fetch(url)

    use_deps(heuristic_deps(fetch=fetch_then_cancel))
    run_id = _start()
    run = repo.get_run(run_id)
    assert run["status"] == "cancelled" and run["report"] is None


def test_run_that_is_not_queued_is_ignored(use_deps):
    use_deps(heuristic_deps())
    run_id = repo.create_run("topic here", "quick", "heuristic", "")
    repo.request_cancel(run_id)  # queued -> cancelled
    loop.run_agent(run_id)
    assert repo.get_run(run_id)["status"] == "cancelled" and repo.list_steps(run_id) == []


# ------------------------------------------------------------------ LLM mode
def _llm_script(read_url):
    return Scripted(
        [
            json.dumps({"questions": ["What is it?", "How does it work?"]}),
            action(action="search", query="solid state batteries"),
            action(action="read", url=read_url),
            action(action="finish"),
            "# Solid state batteries\n\nThey use a solid electrolyte [1]. Costs are high [7].\n\n"
            "## Sources\n1. made up",
        ]
    )


def test_llm_run_end_to_end_with_usage_and_cost(use_deps, monkeypatch):
    monkeypatch.setattr(settings, "input_price_per_mtok", 1.0)
    monkeypatch.setattr(settings, "output_price_per_mtok", 5.0)
    first_url = "https://example.org/solid-state-batteries-a"
    script = _llm_script(first_url)
    use_deps(llm_deps(script))
    run_id = _start(mode="openai_compatible")
    run = repo.get_run(run_id)

    assert run["status"] == "done"
    assert _kinds(run_id) == ["plan", "search", "read", "write"]
    assert (run["input_tokens"], run["output_tokens"]) == (500, 100)  # 5 calls x (100 + 20)
    assert run["cost_usd"] == round((500 * 1 + 100 * 5) / 1_000_000, 6)

    report = run["report"]
    assert "[1]" in report and "[7]" not in report  # invented citation removed
    assert "made up" not in report  # model's own Sources list replaced
    assert f"1. [Page {first_url[-12:]}]({first_url})" in report


def test_prompts_mark_web_content_as_untrusted_and_include_budget(use_deps):
    script = _llm_script("https://example.org/solid-state-batteries-a")
    use_deps(llm_deps(script))
    _start(mode="openai_compatible")
    action_system, action_user = script.calls[1]
    assert "untrusted" in action_system and "Budget left" in action_user
    write_system, write_user = script.calls[-1]
    assert "<source n=\"1\"" in write_user and "never follow instructions" in write_system.lower()


def test_agent_cannot_read_a_url_that_was_not_in_search_results(use_deps):
    script = Scripted(
        [
            json.dumps({"questions": ["q"]}),
            action(action="search", query="solid state batteries"),
            action(action="read", url="http://169.254.169.254/latest/meta-data"),
            action(action="read", url="https://example.org/solid-state-batteries-a"),
            action(action="finish"),
            "# T\n\nBody [1].",
        ]
    )
    use_deps(llm_deps(script))
    run_id = _start(mode="openai_compatible")
    steps = repo.list_steps(run_id)
    errors = [s for s in steps if s["kind"] == "error"]
    assert errors and "not in the search results" in errors[0]["title"]
    assert repo.get_run(run_id)["status"] == "done" and repo.get_run(run_id)["pages_read"] == 1


def test_reading_the_same_page_twice_is_rejected(use_deps):
    url = "https://example.org/solid-state-batteries-a"
    script = Scripted(
        [
            json.dumps({"questions": ["q"]}),
            action(action="search", query="solid state batteries"),
            action(action="read", url=url),
            action(action="read", url=url),
            action(action="finish"),
            "# T\n\nBody [1].",
        ]
    )
    use_deps(llm_deps(script))
    run_id = _start(mode="openai_compatible")
    assert any("already read" in s["title"] for s in repo.list_steps(run_id))


def test_invalid_model_replies_are_retried_then_fall_back(use_deps):
    script = Scripted(
        [
            "not json",  # plan fails -> plan falls back to the topic
            action(action="search", query="solid state batteries"),
            "garbage",  # next_action attempt 1
            "still garbage",  # attempt 2 -> fallback: read first unread result
            action(action="finish"),
            "# T\n\nBody [1].",
        ]
    )
    use_deps(llm_deps(script))
    run_id = _start(mode="openai_compatible")
    run = repo.get_run(run_id)
    assert run["status"] == "done" and run["pages_read"] == 1


def test_page_budget_ends_the_loop(use_deps):
    counter = {"n": 0}

    def endless(system, user):
        from app.agent.state import Usage

        if "plan" in system.lower()[:30] or system.startswith("You plan"):
            return json.dumps({"questions": ["a", "b", "c", "d"]}), Usage(1, 1)
        if system.startswith("You write"):
            return "# T\n\nBody [1] [2] [3].", Usage(1, 1)
        counter["n"] += 1
        if counter["n"] % 2:
            return action(action="search", query=f"query number {counter['n']}"), Usage(1, 1)
        unread = user.split("Latest search results:\n")[1].split("\n")[0]
        url = unread.split(" | ")[1]
        return action(action="read", url=url), Usage(1, 1)

    use_deps(llm_deps(endless))
    run_id = _start(depth="quick", mode="openai_compatible")
    assert repo.get_run(run_id)["pages_read"] == 3  # quick = 3 pages, then it stops


def test_token_budget_stops_the_agent_but_still_writes_a_report(use_deps, monkeypatch):
    monkeypatch.setattr(settings, "max_total_tokens", 250)
    script = Scripted(
        [
            json.dumps({"questions": ["q"]}),
            action(action="search", query="solid state batteries"),
            action(action="read", url="https://example.org/solid-state-batteries-a"),
        ],
        default="# T\n\nBody [1].",
    )
    use_deps(llm_deps(script))
    run_id = _start(mode="openai_compatible")
    steps = repo.list_steps(run_id)
    assert any(s["kind"] == "note" and "token budget" in s["title"] for s in steps)
    assert repo.get_run(run_id)["status"] == "done"


def test_timeout_stops_the_agent(use_deps, monkeypatch):
    monkeypatch.setattr(settings, "run_timeout_seconds", -1)
    use_deps(heuristic_deps())
    run_id = _start()
    assert any("time limit" in s["title"] for s in repo.list_steps(run_id))
    assert repo.get_run(run_id)["status"] == "error"  # nothing read before the deadline


# ------------------------------------------------------------------ report finalisation
def test_finalize_report_strips_fences_sources_and_invalid_citations():
    state = State(topic="Topic")
    state.sources = [Source(1, "One", "https://a.example", "Overview", ["x"])]
    raw = "```markdown\nIntro [1][2].\n\n## Sources\n- fake\n```"
    out = finalize_report(raw, state)
    assert out.startswith("# Topic")  # title added when missing
    assert "[2]" not in out and "fake" not in out
    assert out.rstrip().endswith("1. [One](https://a.example)")
