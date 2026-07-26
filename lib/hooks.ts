"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHistory, fetchPrices } from "./market";
import { STRATEGY_MAP } from "./strategies";
import { usePortfolio } from "./store";
import type { PriceMap } from "./types";

const PRICE_POLL_MS = 45_000;
const BOT_TICK_MS = 90_000;

/** Polls /api/prices and keeps the latest price map. */
export function usePrices() {
  const [prices, setPrices] = useState<PriceMap>({});
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchPrices();
      setPrices(next);
      setError(null);
      setLastUpdated(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch prices");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), PRICE_POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  return { prices, error, lastUpdated, refresh };
}

/**
 * Evaluates every active bot against fresh intraday history on an interval
 * and executes paper trades when a strategy fires. Runs while the app is open.
 */
export function useBotRunner(prices: PriceMap) {
  const { state, dispatch } = usePortfolio();

  // Refs so the interval callback always sees current data without re-arming.
  const stateRef = useRef(state);
  stateRef.current = state;
  const pricesRef = useRef(prices);
  pricesRef.current = prices;
  const runningRef = useRef(false);

  useEffect(() => {
    async function tick() {
      if (runningRef.current) return;
      runningRef.current = true;
      try {
        const bots = stateRef.current.bots.filter((b) => b.active);
        for (const bot of bots) {
          const strategy = STRATEGY_MAP[bot.strategyId];
          if (!strategy) continue;

          try {
            const history = await fetchHistory(bot.coinId, 1);
            const closes = history.map((p) => p[1]);
            const signal = strategy.evaluate(closes, {
              ...strategy.defaults,
              ...bot.params,
            });
            dispatch({ type: "BOT_RESULT", id: bot.id, signal, ts: Date.now() });

            const price = pricesRef.current[bot.coinId]?.price;
            if (!price) continue;

            if (signal.action === "buy" && bot.positionQty <= 0) {
              const budget = Math.min(bot.budgetUsd, stateRef.current.cash);
              if (budget >= 10) {
                dispatch({
                  type: "TRADE",
                  coinId: bot.coinId,
                  side: "buy",
                  qty: budget / price,
                  price,
                  source: "bot",
                  note: `${strategy.name}: ${signal.reason}`,
                  botId: bot.id,
                });
              }
            } else if (signal.action === "sell" && bot.positionQty > 0) {
              dispatch({
                type: "TRADE",
                coinId: bot.coinId,
                side: "sell",
                qty: bot.positionQty,
                price,
                source: "bot",
                note: `${strategy.name}: ${signal.reason}`,
                botId: bot.id,
              });
            }
          } catch {
            // One bot failing (e.g. rate limit) shouldn't stop the others.
          }

          // Space out history fetches to be polite to the API.
          await new Promise((r) => setTimeout(r, 1500));
        }
      } finally {
        runningRef.current = false;
      }
    }

    // First tick shortly after mount so freshly created bots react quickly.
    const first = window.setTimeout(() => void tick(), 5_000);
    const id = window.setInterval(() => void tick(), BOT_TICK_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [dispatch]);
}
