"use client";

import { useState } from "react";
import { COIN_MAP, coinLabel } from "@/lib/coins";
import { fmtUsd } from "@/lib/format";
import { computeEquity, usePortfolio } from "@/lib/store";
import { STRATEGY_MAP } from "@/lib/strategies";
import type { AdvisorResponse, PriceMap } from "@/lib/types";

export default function AdvisorPanel({ prices }: { prices: PriceMap }) {
  const { state, dispatch } = usePortfolio();
  const [loading, setLoading] = useState(false);
  const [advice, setAdvice] = useState<AdvisorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noKey, setNoKey] = useState(false);
  const [applied, setApplied] = useState<Set<number>>(new Set());

  async function askAdvisor() {
    setLoading(true);
    setError(null);
    setNoKey(false);
    setApplied(new Set());

    const snapshot = {
      note: "All values in USD. Paper trading simulation.",
      cash: Math.round(state.cash),
      equity: Math.round(computeEquity(state, prices)),
      startingCash: state.startingCash,
      holdings: Object.values(state.holdings).map((h) => {
        const p = prices[h.coinId]?.price ?? 0;
        return {
          coinId: h.coinId,
          symbol: coinLabel(h.coinId),
          qty: h.qty,
          avgCost: h.avgCost,
          currentPrice: p,
          value: Math.round(h.qty * p),
          unrealizedPnlPct: p ? Number((((p - h.avgCost) / h.avgCost) * 100).toFixed(2)) : 0,
        };
      }),
      market: Object.entries(prices).map(([id, p]) => ({
        coinId: id,
        symbol: coinLabel(id),
        price: p.price,
        change24hPct: Number(p.change24h.toFixed(2)),
      })),
      bots: state.bots.map((b) => ({
        label: `${coinLabel(b.coinId)} ${STRATEGY_MAP[b.strategyId]?.name ?? b.strategyId}`,
        params: b.params,
        active: b.active,
        lastSignal: b.lastSignal ?? null,
      })),
      recentTrades: state.trades.slice(-10).map((t) => ({
        side: t.side,
        symbol: coinLabel(t.coinId),
        value: Math.round(t.value),
        source: t.source,
        realizedPnl: t.realizedPnl != null ? Math.round(t.realizedPnl) : undefined,
      })),
    };

    try {
      const res = await fetch("/api/advise", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(snapshot),
      });
      const body = await res.json();
      if (res.status === 503 && body?.error === "no_key") {
        setNoKey(true);
      } else if (!res.ok) {
        setError(body?.error ?? `Advisor request failed (${res.status})`);
      } else {
        setAdvice(body.advice as AdvisorResponse);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Advisor request failed");
    } finally {
      setLoading(false);
    }
  }

  function applySuggestion(index: number) {
    if (!advice) return;
    const s = advice.suggestions[index];
    const price = prices[s.coinId]?.price;
    if (!price || s.action === "hold") return;

    if (s.action === "buy") {
      const usd = Math.min(s.sizeUsd ?? 1000, state.cash);
      if (usd < 1) return;
      dispatch({
        type: "TRADE",
        coinId: s.coinId,
        side: "buy",
        qty: usd / price,
        price,
        source: "ai",
        note: s.rationale,
      });
    } else {
      const holding = state.holdings[s.coinId];
      if (!holding || holding.qty <= 0) return;
      const qty = s.sizeUsd
        ? Math.min(s.sizeUsd / price, holding.qty)
        : holding.qty;
      dispatch({
        type: "TRADE",
        coinId: s.coinId,
        side: "sell",
        qty,
        price,
        source: "ai",
        note: s.rationale,
      });
    }
    setApplied(new Set(applied).add(index));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <button className="btn primary" onClick={askAdvisor} disabled={loading}>
        {loading ? (
          <>
            <span className="spin" /> Analyzing portfolio…
          </>
        ) : (
          "Ask AI Advisor"
        )}
      </button>

      {noKey && (
        <div className="notice">
          The AI advisor needs an Anthropic API key. Create{" "}
          <code>.env.local</code> in the project root with{" "}
          <code>ANTHROPIC_API_KEY=sk-ant-…</code> and restart the dev server.
          Everything else works without it — strategy bots run locally.
        </div>
      )}

      {error && <div className="error-text">{error}</div>}

      {advice && (
        <>
          <div className="advice-card">
            <strong>Assessment</strong>
            <div className="rationale">{advice.assessment}</div>
          </div>

          {advice.suggestions.map((s, i) => {
            const known = Boolean(COIN_MAP[s.coinId]);
            return (
              <div className="advice-card" key={i}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span className={`badge ${s.action}`}>{s.action}</span>
                  <strong>{coinLabel(s.coinId)}</strong>
                  {s.sizeUsd != null && s.action !== "hold" && (
                    <span className="dim num">{fmtUsd(s.sizeUsd)}</span>
                  )}
                  <span className="faint" style={{ fontSize: 11 }}>
                    {s.confidence} confidence
                  </span>
                  {s.action !== "hold" && known && (
                    <button
                      className="btn sm"
                      style={{ marginLeft: "auto" }}
                      disabled={applied.has(i)}
                      onClick={() => applySuggestion(i)}
                    >
                      {applied.has(i) ? "Applied ✓" : "Apply"}
                    </button>
                  )}
                </div>
                <div className="rationale">{s.rationale}</div>
              </div>
            );
          })}

          {advice.tuning.length > 0 && (
            <div className="advice-card">
              <strong>Bot tuning ideas</strong>
              {advice.tuning.map((t, i) => (
                <div className="rationale" key={i}>
                  <strong style={{ color: "var(--text)" }}>{t.botLabel}:</strong>{" "}
                  {t.suggestion}
                </div>
              ))}
            </div>
          )}

          {advice.riskNotes && (
            <div className="notice">⚠ {advice.riskNotes}</div>
          )}
        </>
      )}

      {!advice && !noKey && !loading && (
        <div className="notice">
          Sends your portfolio, live prices and bot signals to Claude and gets
          back trade ideas with rationale — apply any of them with one click.
          Simulated money only; nothing here is financial advice.
        </div>
      )}
    </div>
  );
}
