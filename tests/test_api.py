import json

from app import repo

from .helpers import heuristic_deps


def _events(text: str) -> list[tuple[str, object]]:
    out = []
    for block in text.strip().split("\n\n"):
        event, data = block.split("\n")
        out.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_health(client):
    body = client.get("/health").json()
    assert body["llm_provider"] == "heuristic" and body["search_provider"] == "wikipedia"


def test_create_run_validates_topic(client):
    assert client.post("/runs", json={"topic": "hi"}).status_code == 422
    assert client.post("/runs", json={"topic": "valid topic", "depth": "huge"}).status_code == 422


def test_full_run_lifecycle(client, use_deps):
    use_deps(heuristic_deps())
    res = client.post("/runs", json={"topic": "solid state batteries", "depth": "quick"})
    assert res.status_code == 202
    run = res.json()
    assert run["status"] == "done" and len(run["steps"]) == 8
    assert run["steps"][1]["kind"] == "search" and run["steps"][1]["detail"]["results"]

    listed = client.get("/runs").json()
    assert [r["id"] for r in listed] == [run["id"]] and "report" not in listed[0]

    fetched = client.get(f"/runs/{run['id']}").json()
    assert fetched["report"].startswith("# solid state batteries")

    md = client.get(f"/runs/{run['id']}/report.md")
    assert md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"]


def test_event_stream_replays_steps_and_ends(client, use_deps):
    use_deps(heuristic_deps())
    run_id = client.post("/runs", json={"topic": "solid state batteries", "depth": "quick"}).json()["id"]

    events = _events(client.get(f"/runs/{run_id}/events").text)
    names = [e for e, _ in events]
    assert names.count("step") == 8 and names[-1] == "end" and "run" in names
    assert events[-2][1]["status"] == "done"

    resumed = _events(client.get(f"/runs/{run_id}/events?after=5").text)
    assert [d["idx"] for e, d in resumed if e == "step"] == [6, 7]


def test_cancel_queued_run_and_delete_rules(client):
    run_id = repo.create_run("some topic", "quick", "heuristic", "")
    assert client.delete(f"/runs/{run_id}").status_code == 409  # still queued

    cancelled = client.post(f"/runs/{run_id}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.delete(f"/runs/{run_id}").status_code == 204
    assert client.get(f"/runs/{run_id}").status_code == 404


def test_missing_runs_return_404(client):
    for path in ("/runs/nope", "/runs/nope/events", "/runs/nope/report.md"):
        assert client.get(path).status_code == 404
    assert client.post("/runs/nope/cancel").status_code == 404


def test_restart_marks_unfinished_runs_as_failed(client):
    run_id = repo.create_run("some topic", "quick", "heuristic", "")
    repo.touch_started(run_id)
    assert repo.mark_interrupted() == 1
    run = repo.get_run(run_id)
    assert run["status"] == "error" and "restart" in run["error"]
