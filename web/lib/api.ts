export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RunStatus = "queued" | "running" | "done" | "error" | "cancelled";
export type Depth = "quick" | "standard" | "deep";

export type Step = {
  idx: number;
  kind: "plan" | "search" | "read" | "write" | "error" | "note";
  title: string;
  detail: Record<string, unknown>;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
};

export type RunSummary = {
  id: string;
  topic: string;
  depth: Depth;
  status: RunStatus;
  mode: string;
  model: string;
  searches: number;
  pages_read: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Run = RunSummary & { report: string | null; steps: Step[] };

export type Health = {
  status: string;
  llm_provider: "heuristic" | "openai_compatible" | "anthropic";
  llm_model: string;
  search_provider: string;
};

export const isActive = (status: RunStatus) => status === "queued" || status === "running";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // keep the generic message
    }
    throw new Error(message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const getHealth = () => request<Health>("/health");
export const listRuns = () => request<RunSummary[]>("/runs");
export const getRun = (id: string) => request<Run>(`/runs/${id}`);
export const cancelRun = (id: string) => request<Run>(`/runs/${id}/cancel`, { method: "POST" });
export const deleteRun = (id: string) => request<void>(`/runs/${id}`, { method: "DELETE" });
export const createRun = (topic: string, depth: Depth) =>
  request<Run>("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, depth }),
  });
export const reportUrl = (id: string) => `${API_URL}/runs/${id}/report.md`;

export type StreamHandlers = {
  onStep: (step: Step) => void;
  onRun: (run: Run) => void;
  onEnd: () => void;
};

/** Subscribes to a run's live event stream. Returns a function that closes it. */
export function openRunStream(id: string, after: number, handlers: StreamHandlers): () => void {
  const source = new EventSource(`${API_URL}/runs/${id}/events?after=${after}`);
  source.addEventListener("step", (e) => handlers.onStep(JSON.parse((e as MessageEvent).data)));
  source.addEventListener("run", (e) => handlers.onRun(JSON.parse((e as MessageEvent).data)));
  source.addEventListener("end", () => {
    source.close();
    handlers.onEnd();
  });
  return () => source.close();
}
