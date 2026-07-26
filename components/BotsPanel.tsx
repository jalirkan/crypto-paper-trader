"use client";

import { useState } from "react";
import { COINS, COIN_MAP } from "@/lib/coins";
import { fmtQty, fmtTime, fmtUsd, uid } from "@/lib/format";
import { usePortfolio } from "@/lib/store";
import { STRATEGIES, STRATEGY_MAP } from "@/lib/strategies";
import type { PriceMap } from "@/lib/types";

export default function BotsPanel({ prices }: { prices: PriceMap }) {
  const { state, dispatch } = usePortfolio();
  const [showForm, setShowForm] = useState(false);
  const [coinId, setCoinId] = useState(COINS[0].id);
  const [strategyId, setStrategyId] = useState(STRATEGIES[0].id);
  const [budget, setBudget] = useState("5000");
  const [params, setParams] = useState<Record<string, number>>({
    ...STRATEGIES[0].defaults,
  });

  const strategy = STRATEGY_MAP[strategyId];

  function selectStrategy(id: string) {
    setStrategyId(id);
    setParams({ ...STRATEGY_MAP[id].defaults });
  }

  function createBot() {
    const budgetUsd = parseFloat(budget) || 0;
    if (budgetUsd < 10) return;
    dispatch({
      type: "ADD_BOT",
      bot: {
        id: uid(),
        coinId,
        strategyId,
        params: { ...params },
        budgetUsd,
        active: true,
        positionQty: 0,
      },
    });
    setShowForm(false);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {state.bots.length === 0 && !showForm && (
        <div className="empty">
          No bots yet. A bot watches one coin with one strategy and paper-trades
          it automatically while the app is open.
        </div>
      )}

      {state.bots.map((bot) => {
        const strat = STRATEGY_MAP[bot.strategyId];
        const coin = COIN_MAP[bot.coinId];
        const price = prices[bot.coinId]?.price;
        const posValue = price ? bot.positionQty * price : 0;
        const signal = bot.lastSignal;
        return (
          <div className="bot-card" key={bot.id}>
            <div className="bot-top">
              <div>
                <div className="bot-title">
                  {coin?.symbol ?? bot.coinId} · {strat?.name ?? bot.strategyId}
                </div>
                <div className="bot-sub num">
                  budget {fmtUsd(bot.budgetUsd)} ·{" "}
                  {bot.positionQty > 0
                    ? `holding ${fmtQty(bot.positionQty)} (${fmtUsd(posValue)})`
                    : "no position"}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button
                  className={`toggle ${bot.active ? "on" : ""}`}
                  title={bot.active ? "Pause bot" : "Activate bot"}
                  onClick={() =>
                    dispatch({
                      type: "UPDATE_BOT",
                      id: bot.id,
                      patch: { active: !bot.active },
                    })
                  }
                />
                <button
                  className="btn sm danger-ghost"
                  title="Remove bot"
                  onClick={() => dispatch({ type: "REMOVE_BOT", id: bot.id })}
                >
                  ✕
                </button>
              </div>
            </div>
            {signal ? (
              <div className="signal-line">
                <span className={`badge ${signal.action}`}>{signal.action}</span>{" "}
                {signal.reason}
                {bot.lastRunTs && (
                  <span className="faint"> · {fmtTime(bot.lastRunTs)}</span>
                )}
              </div>
            ) : (
              <div className="signal-line faint">
                {bot.active
                  ? "Waiting for first evaluation (runs every ~90s)…"
                  : "Paused."}
              </div>
            )}
          </div>
        );
      })}

      {showForm ? (
        <div className="bot-card">
          <div className="form-row">
            <div className="field">
              <label>Coin</label>
              <select value={coinId} onChange={(e) => setCoinId(e.target.value)}>
                {COINS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.symbol} — {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Budget (USD)</label>
              <input
                type="number"
                min="10"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label>Strategy</label>
            <select value={strategyId} onChange={(e) => selectStrategy(e.target.value)}>
              {STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          {strategy && (
            <>
              <div className="bot-sub">{strategy.description}</div>
              <div className="form-row">
                {strategy.params.map((p) => (
                  <div className="field" key={p.key}>
                    <label>{p.label}</label>
                    <input
                      type="number"
                      min={p.min}
                      max={p.max}
                      step={p.step}
                      value={params[p.key] ?? strategy.defaults[p.key]}
                      onChange={(e) =>
                        setParams({
                          ...params,
                          [p.key]: parseFloat(e.target.value) || strategy.defaults[p.key],
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            </>
          )}
          <div className="form-row">
            <button className="btn primary" style={{ flex: 1 }} onClick={createBot}>
              Create bot
            </button>
            <button className="btn" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="btn" onClick={() => setShowForm(true)}>
          + New bot
        </button>
      )}

      {state.bots.some((b) => b.positionQty > 0) && (
        <div className="notice">
          Bots trade from shared portfolio cash and track their own position.
          Signals are evaluated on 5-minute intraday data while the tab is open.
        </div>
      )}
    </div>
  );
}
