"use client";

import { useCallback, useEffect, useState } from "react";
import { fmtUsd } from "@/lib/format";

interface LiveSignal {
  symbol: string;
  strategy: string;
  params: Record<string, number>;
  position: "LONG" | "FLAT";
  since: string;
  days_in_state: number;
  close: number;
  entry_level: number;
  exit_level: number;
}

export default function NarratorPanel() {
  const [signals, setSignals] = useState<LiveSignal[] | null>(null);
  const [serviceDown, setServiceDown] = useState(false);
  const [narration, setNarration] = useState<string | null>(null);
  const [noKey, setNoKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSignals = useCallback(async () => {
    try {
      const res = await fetch("/api/signals");
      if (res.status === 503) {
        setServiceDown(true);
        return;
      }
      const body = await res.json();
      setSignals(body.signals ?? []);
      setServiceDown(false);
    } catch {
      setServiceDown(true);
    }
  }, []);

  useEffect(() => {
    void loadSignals();
    const id = window.setInterval(() => void loadSignals(), 5 * 60_000);
    return () => window.clearInterval(id);
  }, [loadSignals]);

  async function narrate() {
    setLoading(true);
    setError(null);
    setNoKey(false);
    try {
      const res = await fetch("/api/narrate");
      const body = await res.json();
      if (res.status === 503 && body?.error === "no_key") setNoKey(true);
      else if (res.status === 503) setServiceDown(true);
      else if (!res.ok) setError(body?.error ?? `narration failed (${res.status})`);
      else setNarration(body.narration);
    } catch (err) {
      setError(err instanceof Error ? err.message : "narration failed");
    } finally {
      setLoading(false);
    }
  }

  if (serviceDown) {
    return (
      <div className="stack">
        <p className="lede">
          The candidate sleeve is <strong>Donchian breakout with volatility
          targeting</strong> — a 20-day channel, long or flat, sized to a 40%
          annualized volatility target. It decides one thing per symbol per day:
          hold, or stand aside. That decision is written to the forward ledger
          before the next day opens, which is what makes the record
          un-backfillable.
        </p>
        <div className="notice">
          <strong>Today&apos;s live position isn&apos;t shown here</strong>{" "}
          because the signal service isn&apos;t hosted — it reads the archive on
          a machine, not in this browser. Running locally, this panel shows each
          symbol&apos;s position, the price that would flip it, and a plain-language
          briefing written by Claude:{" "}
          <code>python -m research.signal_service</code>.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {signals === null ? (
        <div className="empty">
          <span className="spin" />
        </div>
      ) : (
        signals.map((s) => (
          <div className="advice-card" key={s.symbol}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span className={`badge ${s.position === "LONG" ? "buy" : "hold"}`}>
                {s.position}
              </span>
              <strong>{s.symbol}</strong>
              <span className="dim" style={{ fontSize: 12 }}>
                {s.strategy} ({s.params.entry}-day) · {s.days_in_state}d since {s.since}
              </span>
            </div>
            <div className="rationale num">
              {s.position === "LONG" ? (
                <>exit stop {fmtUsd(s.exit_level)} · now {fmtUsd(s.close)}</>
              ) : (
                <>re-entry above {fmtUsd(s.entry_level)} · now {fmtUsd(s.close)}</>
              )}
            </div>
          </div>
        ))
      )}

      <button className="btn primary" onClick={narrate} disabled={loading}>
        {loading ? (
          <>
            <span className="spin" /> Writing today&apos;s briefing…
          </>
        ) : (
          "Narrate the strategy"
        )}
      </button>

      {noKey && (
        <div className="notice">
          Narration needs <code>ANTHROPIC_API_KEY</code> in <code>.env.local</code>.
          The live signals above work without it.
        </div>
      )}
      {error && <div className="error-text">{error}</div>}
      {narration && (
        <div className="advice-card" style={{ lineHeight: 1.6 }}>
          {narration}
        </div>
      )}
    </div>
  );
}
