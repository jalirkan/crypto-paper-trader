"use client";

import { useEffect, useState } from "react";
import { fmtPct } from "@/lib/format";

interface SymStats {
  symbol: string;
  start?: string;
  days: number;
  note?: string;
  strategy?: { cagr: number; sharpe: number; max_dd: number; exposure?: number };
  buy_hold?: { cagr: number; sharpe: number; max_dd: number };
}

export default function ForwardStats() {
  const [rows, setRows] = useState<SymStats[] | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    fetch("/api/signals")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((body) => setRows(body.forward?.symbols ?? []))
      .catch(() => setDown(true));
  }, []);

  if (down) {
    return (
      <div className="notice">
        Start <code>python -m research.signal_service</code> to see the live
        forward-paper track record here.
      </div>
    );
  }
  if (rows === null) {
    return (
      <div className="empty">
        <span className="spin" />
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="notice">
        The forward-paper ledger records the strategy&apos;s decided position
        every day, live, and can never be backfilled — it began 2026-07-26.
        These numbers are the only performance claims this project stands
        behind; backtests are research, this is the record.
      </div>
      {rows.map((s) =>
        s.strategy && s.buy_hold ? (
          <div className="advice-card" key={s.symbol}>
            <strong>
              {s.symbol} — {s.days} days since {s.start}
            </strong>
            <div className="rationale num">
              strategy: {fmtPct(s.strategy.cagr * 100)} CAGR · Sharpe{" "}
              {s.strategy.sharpe.toFixed(2)} · MaxDD {fmtPct(s.strategy.max_dd * 100, false)}
            </div>
            <div className="rationale num dim">
              buy &amp; hold: {fmtPct(s.buy_hold.cagr * 100)} CAGR · Sharpe{" "}
              {s.buy_hold.sharpe.toFixed(2)} · MaxDD {fmtPct(s.buy_hold.max_dd * 100, false)}
            </div>
          </div>
        ) : (
          <div className="advice-card" key={s.symbol}>
            <strong>{s.symbol}</strong>
            <div className="rationale">
              {s.note ?? "warming up"} — {s.days} day(s) recorded
            </div>
          </div>
        )
      )}
    </div>
  );
}
