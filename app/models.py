from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

Depth = Literal["quick", "standard", "deep"]
RunStatus = Literal["queued", "running", "done", "error", "cancelled"]
TERMINAL = {"done", "error", "cancelled"}


@dataclass(frozen=True)
class Budget:
    pages: int  # pages the agent may read
    steps: int  # total tool calls (searches + reads)


DEPTHS: dict[str, Budget] = {
    "quick": Budget(pages=3, steps=8),
    "standard": Budget(pages=5, steps=12),
    "deep": Budget(pages=8, steps=18),
}


class RunCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    depth: Depth = "standard"


class StepOut(BaseModel):
    idx: int
    kind: str
    title: str
    detail: dict[str, Any]
    duration_ms: int
    input_tokens: int
    output_tokens: int
    created_at: str


class RunSummary(BaseModel):
    id: str
    topic: str
    depth: Depth
    status: RunStatus
    mode: str
    model: str
    searches: int
    pages_read: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class RunOut(RunSummary):
    report: str | None
    steps: list[StepOut]


# --- the action protocol the agent speaks (validated, never trusted) ---
class SearchAction(BaseModel):
    action: Literal["search"]
    query: str = Field(min_length=2, max_length=200)


class ReadAction(BaseModel):
    action: Literal["read"]
    url: str = Field(min_length=8, max_length=2000)


class FinishAction(BaseModel):
    action: Literal["finish"]


Action = Annotated[SearchAction | ReadAction | FinishAction, Field(discriminator="action")]
ActionAdapter: TypeAdapter[SearchAction | ReadAction | FinishAction] = TypeAdapter(Action)
