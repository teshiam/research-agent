import json
import uuid
from typing import Any

from .config import settings
from .db import connect

RUN_FIELDS = {
    "status", "report", "error", "searches", "pages_read", "input_tokens", "output_tokens",
    "started_at", "finished_at", "mode", "model",
}  # fmt: skip


def _cost(row: dict[str, Any]) -> float:
    total = (
        row["input_tokens"] * settings.input_price_per_mtok
        + row["output_tokens"] * settings.output_price_per_mtok
    )
    return round(total / 1_000_000, 6)


def _run(row: Any) -> dict[str, Any]:
    run = dict(row)
    run.pop("cancel_requested", None)
    run["cost_usd"] = _cost(run)
    return run


def create_run(topic: str, depth: str, mode: str, model: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute(
            "INSERT INTO runs (id, topic, depth, mode, model) VALUES (?, ?, ?, ?, ?)",
            (run_id, topic, depth, mode, model),
        )
    return run_id


def get_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _run(row) if row else None


def list_runs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC, rowid DESC").fetchall()
    return [_run(r) for r in rows]


def update_run(run_id: str, **fields: Any) -> None:
    unknown = set(fields) - RUN_FIELDS
    if unknown:
        raise ValueError(f"Cannot update columns: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*fields.values(), run_id))


def touch_started(run_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', started_at = datetime('now') WHERE id = ?",
            (run_id,),
        )


def touch_finished(run_id: str, status: str, **fields: Any) -> None:
    update_run(run_id, status=status, **fields)
    with connect() as conn:
        conn.execute("UPDATE runs SET finished_at = datetime('now') WHERE id = ?", (run_id,))


def request_cancel(run_id: str) -> bool:
    """Queued runs are cancelled immediately; running ones stop at their next step."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE runs SET cancel_requested = 1, "
            "status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END, "
            "finished_at = CASE WHEN status = 'queued' THEN datetime('now') ELSE finished_at END "
            "WHERE id = ? AND status IN ('queued', 'running')",
            (run_id,),
        )
        return cur.rowcount > 0


def is_cancel_requested(run_id: str) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT cancel_requested FROM runs WHERE id = ?", (run_id,)).fetchone()
    return bool(row and row["cancel_requested"])


def delete_run(run_id: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM runs WHERE id = ?", (run_id,)).rowcount > 0


def mark_interrupted() -> int:
    """Runs left 'queued' or 'running' by a restart can never finish: fail them clearly."""
    with connect() as conn:
        return conn.execute(
            "UPDATE runs SET status = 'error', error = 'Interrupted by a server restart.', "
            "finished_at = datetime('now') WHERE status IN ('queued', 'running')"
        ).rowcount


def add_step(
    run_id: str, idx: int, kind: str, title: str, detail: dict[str, Any],
    duration_ms: int = 0, input_tokens: int = 0, output_tokens: int = 0,
) -> None:  # fmt: skip
    with connect() as conn:
        conn.execute(
            "INSERT INTO steps (run_id, idx, kind, title, detail, duration_ms, input_tokens,"
            " output_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, idx, kind, title, json.dumps(detail), duration_ms, input_tokens, output_tokens),
        )


def list_steps(run_id: str, after: int = -1) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT idx, kind, title, detail, duration_ms, input_tokens, output_tokens, created_at "
            "FROM steps WHERE run_id = ? AND idx > ? ORDER BY idx",
            (run_id, after),
        ).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]
