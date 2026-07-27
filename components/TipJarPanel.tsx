"use client";

import { useEffect, useState } from "react";
import { fmtTime } from "@/lib/format";

interface TipsData {
  network: string;
  address: string;
  totals: { count: number; total_sats: number };
  recent: Array<{ ts: number; sats: number; comment: string }>;
}

export default function TipJarPanel() {
  const [data, setData] = useState<TipsData | null>(null);
  const [down, setDown] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch("/api/tipjar")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setDown(true));
  }, []);

  if (down) {
    return (
      <div className="notice">
        ⚡ The Lightning tip jar isn&apos;t online yet — it goes live with the
        VPS deployment (signet first, then mainnet). The stack is built and
        tested; see <code>deploy/vps/README.md</code>.
      </div>
    );
  }
  if (!data) {
    return (
      <div className="empty">
        <span className="spin" />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="advice-card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="badge ai">⚡ {data.network}</span>
          <code style={{ fontSize: 13 }}>{data.address}</code>
          <button
            className="btn sm"
            onClick={() => {
              void navigator.clipboard.writeText(data.address);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <div className="rationale">
          Tips fund the live experiment&apos;s eventual micro-capital — donations
          only, nothing promised in return. {data.totals.count} tips ·{" "}
          <span className="num">{data.totals.total_sats.toLocaleString()}</span> sats
          received.
        </div>
      </div>
      {data.recent.length > 0 && (
        <div className="advice-card">
          <strong>Recent</strong>
          {data.recent.slice(0, 8).map((t, i) => (
            <div className="rationale num" key={i}>
              {t.sats.toLocaleString()} sats
              {t.comment && <> — “{t.comment}”</>}{" "}
              <span className="faint">{fmtTime(t.ts)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
