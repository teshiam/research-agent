"use client";

import { useState } from "react";
import type { Depth, RunSummary } from "@/lib/api";
import { StatusPill } from "./RunView";

const DEPTHS: { value: Depth; label: string; hint: string }[] = [
  { value: "quick", label: "Quick", hint: "3 pages" },
  { value: "standard", label: "Standard", hint: "5 pages" },
  { value: "deep", label: "Deep", hint: "8 pages" },
];

const EXAMPLES = ["Solid-state batteries", "History of the printing press", "How does CRISPR work"];

type Props = {
  runs: RunSummary[];
  selectedId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onCreate: (topic: string, depth: Depth) => Promise<void>;
};

export default function Sidebar({ runs, selectedId, disabled, onSelect, onCreate }: Props) {
  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState<Depth>("quick");
  const [busy, setBusy] = useState(false);

  async function submit(value: string) {
    const text = value.trim();
    if (text.length < 3 || busy) return;
    setBusy(true);
    await onCreate(text, depth);
    setTopic("");
    setBusy(false);
  }

  return (
    <aside className="sidebar">
      <form className="new" onSubmit={(e) => { e.preventDefault(); void submit(topic); }}>
        <label htmlFor="topic">Research topic</label>
        <textarea
          id="topic" rows={3} value={topic} maxLength={300}
          placeholder="What do you want to find out?"
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(topic); } }}
        />
        <div className="seg" role="radiogroup" aria-label="Research depth">
          {DEPTHS.map((d) => (
            <button key={d.value} type="button" role="radio" aria-checked={depth === d.value}
              className={`seg-btn${depth === d.value ? " seg-on" : ""}`} onClick={() => setDepth(d.value)}>
              {d.label}<small>{d.hint}</small>
            </button>
          ))}
        </div>
        <button type="submit" className="btn btn-primary" disabled={disabled || busy || topic.trim().length < 3}>
          {busy ? "Starting…" : "Start research"}
        </button>
        <div className="chips">
          {EXAMPLES.map((e) => (
            <button key={e} type="button" className="chip" disabled={disabled || busy} onClick={() => void submit(e)}>{e}</button>
          ))}
        </div>
      </form>

      <div className="runs-title">History</div>
      <ul className="runs">
        {runs.length === 0 && <li className="muted small">No research yet.</li>}
        {runs.map((r) => (
          <li key={r.id}>
            <button type="button" className={`run-item${r.id === selectedId ? " run-item-on" : ""}`} onClick={() => onSelect(r.id)}>
              <span className="run-topic">{r.topic}</span>
              <span className="run-meta"><StatusPill status={r.status} /><span className="muted small">{r.pages_read} pages</span></span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
