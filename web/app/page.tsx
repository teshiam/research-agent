"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import RunView from "@/components/RunView";
import Sidebar from "@/components/Sidebar";
import {
  cancelRun, createRun, deleteRun, getHealth, getRun, isActive, listRuns, openRunStream,
  type Depth, type Health, type Run, type RunSummary, type Step,
} from "@/lib/api";

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeStream = useRef<(() => void) | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const [h, r] = await Promise.all([getHealth(), listRuns()]);
      setHealth(h);
      setRuns(r);
      setOffline(false);
      return r;
    } catch {
      setOffline(true);
      return [];
    }
  }, []);

  useEffect(() => {
    void refreshRuns().then((r) => { if (r.length > 0) setSelectedId(r[0].id); });
  }, [refreshRuns]);

  // Load the selected run, then follow it live while the agent is still working.
  useEffect(() => {
    closeStream.current?.();
    closeStream.current = null;
    if (!selectedId) { setRun(null); return; }

    let cancelled = false;
    getRun(selectedId)
      .then((loaded) => {
        if (cancelled) return;
        setRun(loaded);
        if (!isActive(loaded.status)) return;
        const last = loaded.steps.length ? loaded.steps[loaded.steps.length - 1].idx : -1;
        closeStream.current = openRunStream(selectedId, last, {
          onStep: (step: Step) =>
            setRun((cur) => cur && !cur.steps.some((s) => s.idx === step.idx) ? { ...cur, steps: [...cur.steps, step] } : cur),
          onRun: (update) => setRun((cur) => (cur ? { ...cur, ...update, steps: cur.steps } : cur)),
          onEnd: () => void refreshRuns(),
        });
      })
      .catch(() => setSelectedId(null));

    return () => { cancelled = true; closeStream.current?.(); };
  }, [selectedId, refreshRuns]);

  async function handleCreate(topic: string, depth: Depth) {
    setError(null);
    try {
      const created = await createRun(topic, depth);
      await refreshRuns();
      setSelectedId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the research.");
    }
  }

  async function handleCancel() {
    if (!run) return;
    try { setRun(await cancelRun(run.id)); await refreshRuns(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not cancel."); }
  }

  async function handleDelete() {
    if (!run || !window.confirm("Delete this research run?")) return;
    try {
      await deleteRun(run.id);
      const remaining = await refreshRuns();
      setSelectedId(remaining[0]?.id ?? null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not delete."); }
  }

  const freeMode = health?.llm_provider === "heuristic";
  const modeLabel = offline ? "API offline" : !health ? "Connecting…"
    : freeMode ? `Free mode · ${health.search_provider}` : `LLM · ${health.llm_model} · ${health.search_provider}`;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true">R</span>
          <span className="brand-name">ResearchAgent</span>
        </div>
        <span className={`status${offline ? " status-off" : ""}`}><span className="dot" />{modeLabel}</span>
      </header>

      {offline && <div className="banner" role="alert">Can&apos;t reach the API. Start it with <code>uvicorn app.main:app --reload</code>.</div>}
      {error && <div className="banner" role="alert">{error}</div>}

      <div className="workspace">
        <Sidebar runs={runs} selectedId={selectedId} disabled={offline} onSelect={setSelectedId} onCreate={handleCreate} />
        <main className="panel">
          {run ? (
            <RunView run={run} freeMode={freeMode} onCancel={handleCancel} onDelete={handleDelete} />
          ) : (
            <div className="welcome">
              <h1>Research any topic, with sources</h1>
              <p className="muted">
                The agent plans research questions, searches, reads pages, and writes a report where every
                claim is cited. Watch each step happen live.
              </p>
              {freeMode && (
                <p className="hint">
                  <strong>Free mode:</strong> no language model is connected, so the agent follows a scripted
                  plan over Wikipedia and assembles an extractive report. Connect a free LLM in <code>.env</code> for
                  a written synthesis.
                </p>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
