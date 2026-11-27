import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import loop
from app.config import settings
from app.db import init_db


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "llm_provider", "heuristic")
    monkeypatch.setattr(settings, "run_inline", True)
    monkeypatch.setattr(settings, "sse_poll_seconds", 0)
    monkeypatch.setattr(settings, "input_price_per_mtok", 0.0)
    monkeypatch.setattr(settings, "output_price_per_mtok", 0.0)
    init_db()


@pytest.fixture()
def use_deps(monkeypatch):
    def apply(deps):
        monkeypatch.setattr(loop, "default_deps", lambda: deps)

    return apply


@pytest.fixture()
def client():
    # No `with` block: the lifespan would also start a thread pool we don't want in tests.
    return TestClient(main.app)
