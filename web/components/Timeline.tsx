"use client";

import type { Step } from "@/lib/api";

const ICON: Record<Step["kind"], string> = {
  plan: "P", search: "S", read: "R", write: "W", error: "!", note: "i",
};

type SearchResult = { title: string; url: string; snippet: string };

function Detail({ step }: { step: Step }) {
  const d = step.detail;
  if (step.kind === "plan") {
    const questions = (d.questions as string[]) ?? [];
    return <ol className="detail-list">{questions.map((q) => <li key={q}>{q}</li>)}</ol>;
  }
  if (step.kind === "search") {
    const results = (d.results as SearchResult[]) ?? [];
    if (results.length === 0) return <p className="muted small">No results.</p>;
    return (
      <ul className="detail-list">
        {results.map((r) => (
          <li key={r.url}>
            <strong>{r.title}</strong>
            <span className="muted small url">{r.url}</span>
            {r.snippet && <span className="muted small">{r.snippet}</span>}
          </li>
        ))}
      </ul>
    );
  }
  if (step.kind === "read") {
    const excerpts = (d.excerpts as string[]) ?? [];
    return (
      <>
        <p className="muted small url">{String(d.url)} · {String(d.chars)} characters read</p>
        <ul className="detail-list">{excerpts.map((e) => <li key={e}>{e}</li>)}</ul>
      </>
    );
  }
  return null;
}

export default function Timeline({ steps, active }: { steps: Step[]; active: boolean }) {
  return (
    <ol className="timeline" aria-label="Agent steps">
      {steps.map((step) => {
        const hasDetail = ["plan", "search", "read"].includes(step.kind);
        const tokens = step.input_tokens + step.output_tokens;
        return (
          <li key={step.idx} className={`step step-${step.kind}`}>
            <span className="step-icon" aria-hidden="true">{ICON[step.kind]}</span>
            <div className="step-body">
              {hasDetail ? (
                <details>
                  <summary>{step.title}</summary>
                  <Detail step={step} />
                </details>
              ) : (
                <span className="step-title">{step.title}</span>
              )}
              <span className="muted small">
                {(step.duration_ms / 1000).toFixed(1)}s{tokens > 0 && ` · ${tokens.toLocaleString()} tokens`}
              </span>
            </div>
          </li>
        );
      })}
      {active && (
        <li className="step step-live">
          <span className="step-icon pulse" aria-hidden="true">…</span>
          <div className="step-body"><span className="muted">Working…</span></div>
        </li>
      )}
    </ol>
  );
}
