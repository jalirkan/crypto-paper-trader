"use client";

import { useEffect, useState } from "react";

/** Renders research/experiments.md — split into entry cards, verdicts badged. */
export default function ExperimentsLedger() {
  const [entries, setEntries] = useState<Array<{ title: string; body: string }> | null>(null);

  useEffect(() => {
    fetch("/api/experiments")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(({ markdown }: { markdown: string }) => {
        const parts = markdown.split(/^## /m).slice(1);
        setEntries(
          parts.map((p) => {
            const [title, ...rest] = p.split("\n");
            return { title: title.trim(), body: rest.join("\n").trim() };
          })
        );
      })
      .catch(() => setEntries([]));
  }, []);

  if (entries === null) {
    return (
      <div className="empty">
        <span className="spin" />
      </div>
    );
  }
  if (entries.length === 0) {
    return <div className="empty">Ledger unavailable.</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {entries.map((e, i) => {
        const killed = /KILL/.test(e.body) && !/KEEP/.test(e.body);
        return (
          <details className="advice-card" key={i} open={i >= entries.length - 2}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>
              <span className={`badge ${killed ? "sell" : "buy"}`} style={{ marginRight: 8 }}>
                {killed ? "killed" : "findings"}
              </span>
              {e.title}
            </summary>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                lineHeight: 1.6,
                color: "var(--text-dim)",
                marginTop: 8,
              }}
            >
              {e.body}
            </pre>
          </details>
        );
      })}
    </div>
  );
}
