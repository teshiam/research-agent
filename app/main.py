import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from . import repo
from .agent.loop import run_agent
from .config import settings
from .db import init_db
from .models import TERMINAL, RunCreate, RunOut, RunSummary

_pool: ThreadPoolExecutor | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _pool
    init_db()
    repo.mark_interrupted()
    _pool = ThreadPoolExecutor(max_workers=max(1, settings.max_concurrent_runs))
    yield
    _pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="ResearchAgent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _full(run_id: str) -> dict:
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {**run, "steps": repo.list_steps(run_id)}


@app.get("/health")
def health() -> dict[str, str]:
    heuristic = settings.llm_provider == "heuristic"
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_model": "" if heuristic else settings.llm_model,
        "search_provider": settings.search_provider,
    }


@app.post("/runs", response_model=RunOut, status_code=202)
def create_run(req: RunCreate) -> dict:
    run_id = repo.create_run(
        req.topic.strip(), req.depth, settings.llm_provider, settings.llm_model
    )
    if settings.run_inline or _pool is None:
        run_agent(run_id)
    else:
        _pool.submit(run_agent, run_id)
    return _full(run_id)


@app.get("/runs", response_model=list[RunSummary])
def list_runs() -> list[dict]:
    return repo.list_runs()


@app.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str) -> dict:
    return _full(run_id)


@app.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str) -> dict:
    if repo.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    repo.request_cancel(run_id)
    return _full(run_id)


@app.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str) -> None:
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run["status"] not in TERMINAL:
        raise HTTPException(409, "Cancel the run before deleting it.")
    repo.delete_run(run_id)


@app.get("/runs/{run_id}/report.md", response_class=PlainTextResponse)
def download_report(run_id: str) -> PlainTextResponse:
    run = repo.get_run(run_id)
    if run is None or not run["report"]:
        raise HTTPException(404, "No report available")
    return PlainTextResponse(
        run["report"],
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="research-{run_id}.md"'},
    )


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/runs/{run_id}/events")
def run_events(run_id: str, after: int = Query(-1, ge=-1)) -> StreamingResponse:
    """Server-sent events: `step` as each step lands, `run` on progress, `end` when finished."""
    if repo.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")

    def stream() -> Iterator[str]:
        last, signature = after, None
        while True:
            run = repo.get_run(run_id)
            if run is None:
                yield _sse("end", {})
                return
            for step in repo.list_steps(run_id, after=last):
                yield _sse("step", step)
                last = step["idx"]
            summary = {k: v for k, v in run.items()}
            sig = (run["status"], run["searches"], run["pages_read"], run["input_tokens"])
            if sig != signature:
                signature = sig
                yield _sse("run", summary)
            if run["status"] in TERMINAL:
                yield _sse("end", {})
                return
            time.sleep(settings.sse_poll_seconds)

    return StreamingResponse(stream(), media_type="text/event-stream")
