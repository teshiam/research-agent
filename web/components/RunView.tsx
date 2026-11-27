"use client";

import { isActive, reportUrl, type Run } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import Timeline from "./Timeline";

export const STATUS_LABEL: Record<Run["status"], string> = {
  queued: "Queued", running: "Researching", done: "Done", error: "Failed", cancelled: "Cancelled",
};

export function StatusPill({ status }: { status: Run["status"] }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABEL[status]}</span>;
}

function seconds(run: Run): number | null {
  const start = run.started_at ?? run.created_at;
  const end = run.finished_at;
  if (!end) return null;
  return Math.max(0, (Date.parse(end + "Z") - Date.parse(start + "Z")) / 1000);
}

type Props = {
  run: Run;
  freeMode: boolean;
  onCancel: () => void;
  onDelete: () => void;
};

export default function RunView({ run, freeMode, onCancel, onDelete }: Props) {
  const active = isActive(run.status);
  const tokens = run.input_tokens + run.output_tokens;
  const duration = seconds(run);

  async function copyReport() {
    if (run.report) await navigator.clipboard.writeText(run.report);
  }

  return (
    <article className="run">
      <header className="run-head">
        <div>
          <h2>{run.topic}</h2>
          <p className="muted small">{run.depth} depth · {freeMode ? "free mode" : run.model || run.mode}</p>
        </div>
        <div className="run-actions">
          <StatusPill status={run.status} />
          {active ? (
            <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          ) : (
            <button type="button" className="btn btn-danger" onClick={onDelete}>Delete</button>
          )}
        </div>
      </header>

      <dl className="stats">
        <div><dt>Searches</dt><dd>{run.searches}</dd></div>
        <div><dt>Pages read</dt><dd>{run.pages_read}</dd></div>
        <div><dt>Tokens</dt><dd>{tokens.toLocaleString()}</dd></div>
        <div><dt>Est. cost</dt><dd>${run.cost_usd.toFixed(4)}</dd></div>
        <div><dt>Time</dt><dd>{duration === null ? "…" : `${duration.toFixed(1)}s`}</dd></div>
      </dl>

      {run.error && <div className="inline-error" role="alert">{run.error}</div>}

      <div className="run-cols">
        <section className="card">
          <h3>Agent steps</h3>
          <Timeline steps={run.steps} active={active} />
        </section>

        <section className="card card-report">
          <div className="report-head">
            <h3>Report</h3>
            {run.report && (
              <div className="run-actions">
                <button type="button" className="btn btn-sm" onClick={copyReport}>Copy</button>
                <a className="btn btn-sm" href={reportUrl(run.id)}>Download .md</a>
              </div>
            )}
          </div>
          {run.report ? (
            <Markdown text={run.report} />
          ) : (
            <p className="muted">{active ? "The report appears here when the agent finishes." : "No report."}</p>
          )}
        </section>
      </div>
    </article>
  );
}
