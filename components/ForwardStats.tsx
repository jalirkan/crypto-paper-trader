"use client";

import { useEffect, useState } from "react";
import { fmtPct } from "@/lib/format";
import Figure from "./Figure";
import ForwardCurve from "./ForwardCurve";

/**
 * The forward-paper track record — the only performance claim this project is
 * willing to stand behind, and therefore the panel most able to mislead.
 *
 * Three rules are enforced here rather than left to judgment:
 *
 *   1. Every number comes from the payload. An earlier version of this file
 *      hardcoded the ledger's start date and rendered a "6 / 90 days" progress
 *      bar computed from that constant — while the forward_paper table did not
 *      exist and held no rows. It looked like a measurement and was arithmetic
 *      on a literal. Nothing here is derived from a date typed into the source.
 *   2. Sample size is shown before any performance number.
 *   3. CAGR and Sharpe are WITHHELD until the ledger clears the 90-day gate
 *      from RESEARCH_PLAN §7. A Sharpe over a handful of days is noise with a
 *      decimal point. The equity curve is shown as soon as there are points,
 *      because a plotted series carries its own sample size: you can see how
 *      short it is.
 */

/** RESEARCH_PLAN §7: no "profitable" claim without ≥3 months of forward paper. */
const CLAIM_GATE_DAYS = 90;

interface Curve {
  days: string[];
  strategy: number[];
  buy_hold: number[];
}

interface SymStats {
  symbol: string;
  start?: string;
  days: number;
  note?: string;
  strategy?: { cagr: number; sharpe: number; max_dd: number; exposure?: number };
  buy_hold?: { cagr: number; sharpe: number; max_dd: number };
  curve?: Curve;
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
        estimated. A Sharpe ratio over {days} recorded day
        {days === 1 ? "" : "s"} carries no information, and publishing one would
        undercut every other number on this page.
      </div>
    </div>
  );
}

export default function ForwardStats() {
  const [rows, setRows] = useState<SymStats[] | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    fetch("/api/signals")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => setRows(body.forward?.symbols ?? []))
      .catch(() => setDown(true));
  }, []);

  const recorded = rows?.reduce((m, s) => Math.max(m, s.days ?? 0), 0) ?? 0;
  const started = recorded > 0;

  return (
    <div className="stack">
      <p className="lede">
        The forward ledger records the strategy&apos;s decided position every
        day, live, and can never be backfilled. Backtests are research; this is
        the record — and it is the only thing here that improves with time
        rather than with cleverness.
      </p>

      {down ? (
        <div className="notice">
          <strong>The signal service is not hosted, so this panel has no
          data.</strong>{" "}
          It is a local Python service (
          <code>python -m research.signal_service</code>) that reads the ledger
          out of the archive on a machine, not in this browser. How long the
          record is, and whether it has started at all, are facts that live in
          that archive — this page will not guess at them from a date written
          into its own source.
        </div>
      ) : rows === null ? (
        <div className="empty">
          <span className="spin" />
        </div>
      ) : !started ? (
        <div className="notice">
          <strong>The forward-paper clock has not started.</strong> The ledger
          holds no recorded days yet. It begins on the first run of{" "}
          <code>python -m collectors.run</code>, which records each
          symbol&apos;s decided position once per day; until then there is no
          track record, and this panel would rather say so than display an
          empty chart with confident axes.
        </div>
      ) : (
        <>
          <Gate days={recorded} />
          <div className="fwd-grid">
            {rows.map((s) => {
              const n = s.days ?? 0;
              const showStats = n >= CLAIM_GATE_DAYS && s.strategy && s.buy_hold;
              return (
                <div className="fwd-card" key={s.symbol}>
                  <div className="fwd-head">
                    <strong>{s.symbol}</strong>
                    <span className="num faint">
                      {n} day{n === 1 ? "" : "s"} recorded
                      {s.start ? ` since ${s.start}` : ""}
                    </span>
                  </div>

                  {s.curve && s.curve.strategy.length > 1 ? (
                    <ForwardCurve
                      days={s.curve.days}
                      strategy={s.curve.strategy}
                      buyHold={s.curve.buy_hold}
                    />
                  ) : null}

                  {showStats ? (
                    <div className="fwd-figs">
                      <Figure
                        label="Strategy CAGR"
                        value={fmtPct(s.strategy!.cagr * 100)}
                        n={n}
                        nUnit="days"
                        noCi="interval not yet computed on the forward ledger"
                        // Coloured against the benchmark, not against zero.
                        // PLAN §2.1: every strategy is measured against
                        // buy-and-hold, always. A positive return that lost to
                        // holding is not a green number, and painting it green
                        // is how a page flatters its own strategy.
                        tone={s.strategy!.cagr >= s.buy_hold!.cagr ? "good" : "bad"}
                        note={`${fmtPct(
                          (s.strategy!.cagr - s.buy_hold!.cagr) * 100
                        )} vs buy & hold`}
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
                      performance statistics withheld until the{" "}
                      {CLAIM_GATE_DAYS}-day gate opens
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
