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
        ⚡ <strong>The Lightning tip jar has no node attached yet.</strong> The
        stack is written and tested offline — a custom LNURL-pay and Lightning
        Address implementation (LUD-06/12/16) against LND&apos;s REST API, with
        the web service confined to an invoice-only macaroon so it can create
        invoices but never spend. It needs a funded node to go live. Run it with
        no infrastructure at all: <code>python -m lightning.service --demo</code>.
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
