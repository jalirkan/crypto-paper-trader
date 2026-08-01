"use client";

import { useEffect, useState } from "react";
import { fmtPct } from "@/lib/format";
import Figure from "./Figure";

/**
 * The forward-paper track record — the only performance claim this project is
 * willing to stand behind, and therefore the panel most able to mislead.
 *
 * Two rules are enforced here rather than left to judgment:
 *   1. Sample size is shown before any performance number, always.
 *   2. CAGR / Sharpe are WITHHELD until the forward ledger clears the 90-day
 *      gate from RESEARCH_PLAN §7. A Sharpe computed over five days is noise
 *      with a decimal point, and rendering it "just to have something there"
 *      is precisely the failure this project documents itself avoiding.
 */

/** RESEARCH_PLAN §7: no "profitable" claim without ≥3 months of forward paper. */
const CLAIM_GATE_DAYS = 90;
/** First day written to the immutable forward ledger. */
const LEDGER_START = "2026-07-26";

interface SymStats {
  symbol: string;
  start?: string;
  days: number;
  note?: string;
  strategy?: { cagr: number; sharpe: number; max_dd: number; exposure?: number };
  buy_hold?: { cagr: number; sharpe: number; max_dd: number };
}

function daysSince(iso: string): number {
  const ms = Date.now() - new Date(`${iso}T00:00:00Z`).getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

function Gate({ days }: { days: number }) {
  const pct = Math.min(100, (days / CLAIM_GATE_DAYS) * 100);
  return (
    <div className="gate">
      <div className="gate-row">
        <span className="gate-label">Progress to the first publishable claim</span>
        <span className="num gate-count">
          {days} / {CLAIM_GATE_DAYS} days
        </span>
      </div>
      <div className="gate-track">
        <div className="gate-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="gate-note">
        Until this bar fills, performance statistics are withheld rather than
        estimated. A Sharpe ratio over {days} day{days === 1 ? "" : "s"} carries
        no information, and publishing one would undercut every other number on
        this page.
      </div>
    </div>
  );
}

export default function ForwardStats() {
  const [rows, setRows] = useState<SymStats[] | null>(null);
  const [down, setDown] = useState(false);
  const elapsed = daysSince(LEDGER_START);

  useEffect(() => {
    fetch("/api/signals")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => setRows(body.forward?.symbols ?? []))
      .catch(() => setDown(true));
  }, []);

  const openGate = elapsed >= CLAIM_GATE_DAYS;

  return (
    <div className="stack">
      <p className="lede">
        The forward ledger records the strategy&apos;s decided position every
        day, live, and can never be backfilled. It began{" "}
        <strong className="num">{LEDGER_START}</strong>. Backtests are research;
        this is the record — and it is the only thing here that improves with
        time rather than with cleverness.
      </p>

      <Gate days={elapsed} />

      {down ? (
        <div className="notice">
          <strong>The signal service is not hosted yet.</strong> It is a local
          Python service (<code>python -m research.signal_service</code>) that
          reads the forward ledger out of the archive; the public site has no
          backend attached. The gate above is computed from the ledger&apos;s
          start date, which is a fixed fact — but the per-symbol positions below
          need the service running.
        </div>
      ) : rows === null ? (
        <div className="empty">
          <span className="spin" />
        </div>
      ) : rows.length === 0 ? (
        <div className="notice">The forward ledger has no rows yet.</div>
      ) : (
        <div className="fwd-grid">
          {rows.map((s) => {
            const n = s.days ?? 0;
            const showStats = openGate && s.strategy && s.buy_hold;
            return (
              <div className="fwd-card" key={s.symbol}>
                <div className="fwd-head">
                  <strong>{s.symbol}</strong>
                  <span className="num faint">
                    {n} day{n === 1 ? "" : "s"} recorded
                    {s.start ? ` since ${s.start}` : ""}
                  </span>
                </div>
                {showStats ? (
                  <div className="fwd-figs">
                    <Figure
                      label="Strategy CAGR"
                      value={fmtPct(s.strategy!.cagr * 100)}
                      n={n}
                      nUnit="days"
                      noCi="interval not yet computed on the forward ledger"
                      tone={s.strategy!.cagr >= 0 ? "good" : "bad"}
                    />
                    <Figure
                      label="Buy & hold CAGR"
                      value={fmtPct(s.buy_hold!.cagr * 100)}
                      n={n}
                      nUnit="days"
                      noCi="benchmark, same window"
                    />
                  </div>
                ) : (
                  <div className="fwd-withheld">
                    {s.note ? `${s.note} — ` : ""}
                    performance statistics withheld until the {CLAIM_GATE_DAYS}-day
                    gate opens
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
